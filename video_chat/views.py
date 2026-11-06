import json
import logging
import os
import re
import time
import uuid

import requests
import twilio.jwt.access_token
import twilio.jwt.access_token.grants
import twilio.rest
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from openai import OpenAI
from pydub import AudioSegment
from twilio.base.exceptions import TwilioRestException

from .decorators import login_required_json
from .models import Recording
from .services import RecordingService

logger = logging.getLogger('video_chat')

# Twilio の録音 SID は "RT" + 32 桁の16進数
RECORDING_SID_RE = re.compile(r'^RT[0-9a-fA-F]{32}$')
ROOM_RECORDINGS_CACHE_TIMEOUT = 300  # 署名付き URL の有効期限より短くする
TRANSCRIBED_SIDS_SESSION_KEY = 'transcribed_recording_sids'


class RoomManager:
    def __init__(self, twilio_client):
        self.twilio_client = twilio_client
        self.lock_timeout = 30

    def _cleanup_existing_room(self, room_name):
        """既存のルームをクリーンアップする"""
        try:
            rooms = self.twilio_client.video.rooms.list(unique_name=room_name, status='in-progress')

            for room in rooms:
                try:
                    logger.info(f"Completing room: {room.sid}")
                    self.twilio_client.video.rooms(room.sid).update(status='completed')
                    cache.delete(f'room_{room_name}')
                    cache.delete(f'recording_rules_{room.sid}')
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error completing room {room.sid}: {e}")

            # Twilio 側に変更が反映されるのを待つ
            time.sleep(3)

        except Exception as e:
            # クリーンアップの失敗は致命的ではないので、例外は発生させない
            logger.error(f"Error in cleanup: {e}")

    def get_or_create_room(self, room_name, max_retries=3, delay=1):
        """ロックを使用して部屋を取得または作成"""
        try:
            existing_room = self.twilio_client.video.rooms(room_name).fetch()
            if existing_room.status != 'completed':
                logger.info(f"Found active room: {room_name}")
                self._ensure_recording_rules(existing_room.sid)
                return existing_room
        except TwilioRestException as e:
            if e.code != 20404:  # Room not found 以外のエラー
                logger.error(f"Unexpected Twilio error: {e}")

        lock_key = f'room_lock_{room_name}'

        for attempt in range(max_retries):
            if cache.add(lock_key, True, self.lock_timeout):
                try:
                    self._cleanup_existing_room(room_name)
                    room = self._create_new_room(room_name)
                    if room:
                        return room
                finally:
                    cache.delete(lock_key)
            else:
                logger.info(f"Waiting for lock on room: {room_name} (attempt {attempt + 1})")
                time.sleep(delay)

                # ロック待機中に他のプロセスが作成した可能性をチェック
                try:
                    room = self.twilio_client.video.rooms(room_name).fetch()
                    if room.status != 'completed':
                        logger.info(f"Found room created by another process: {room_name}")
                        self._ensure_recording_rules(room.sid)
                        return room
                except TwilioRestException:
                    pass

        logger.warning(f"Failed to acquire lock, attempting final room creation: {room_name}")
        room = self._create_new_room(room_name)
        if room:
            return room
        raise RuntimeError("Failed to create or acquire room")

    def _create_new_room(self, room_name):
        """新しいルームを作成する"""
        create_kwargs = {
            'unique_name': room_name,
            'type': 'group',
            'record_participants_on_connect': True,
            'video_codecs': ['VP8', 'H264'],
        }
        if settings.TWILIO_STATUS_CALLBACK_URL:
            create_kwargs['status_callback'] = settings.TWILIO_STATUS_CALLBACK_URL

        for create_attempt in range(3):
            try:
                room = self.twilio_client.video.rooms.create(**create_kwargs)
                logger.info(f"Created new room: {room_name} (SID: {room.sid})")

                self._set_recording_rules(room.sid)

                cache.set(f'room_{room_name}', {'sid': room.sid, 'status': room.status}, timeout=3600)
                return room

            except TwilioRestException as e:
                if e.code == 53113:  # Room exists エラー
                    logger.warning(f"Room still exists, retrying after cleanup (attempt {create_attempt + 1})")
                    time.sleep(2)
                    continue
                raise

        return None

    def _set_recording_rules(self, room_sid):
        """録音ルールを設定する（identity が "student" の参加者の音声だけを録音）"""
        rules = [{'type': 'include', 'kind': 'audio', 'publisher': 'student'}]

        try:
            time.sleep(1)
            self.twilio_client.video.rooms(room_sid).recording_rules.update(rules=rules)

            updated_rules = self.twilio_client.video.rooms(room_sid).recording_rules.fetch()
            if updated_rules and updated_rules.rules:
                logger.info(f"Successfully set recording rules for room: {room_sid}")
                cache.set(f'recording_rules_{room_sid}', rules, timeout=3600)
            else:
                raise RuntimeError("Failed to verify recording rules")

        except Exception as e:
            logger.error(f"Error setting recording rules: {e}")
            raise

    def _ensure_recording_rules(self, room_sid):
        """録音ルールが設定されているか確認し、必要に応じて設定する"""
        try:
            if not cache.get(f'recording_rules_{room_sid}'):
                current_rules = self.twilio_client.video.rooms(room_sid).recording_rules.fetch()
                if not current_rules or not current_rules.rules:
                    self._set_recording_rules(room_sid)
        except Exception as e:
            # エラーは無視してルームの使用を継続
            logger.error(f"Error ensuring recording rules: {e}")


# Twilio クライアントの初期化
try:
    twilio_client = twilio.rest.Client(
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_SECRET,
        settings.TWILIO_ACCOUNT_SID,
    )
except Exception as e:
    logger.error(f"Failed to initialize Twilio client: {e}")
    twilio_client = None


def get_access_token(room_name, user_type=None):
    """アクセストークンを生成する"""
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_API_KEY_SID, settings.TWILIO_API_SECRET]):
        raise ValueError("Twilio credentials are not properly configured")

    # 録音ルールが publisher="student" で絞り込んでいるため、identity はロール名そのものにする。
    # （同じルームに student が2人いると衝突するので、1対1レッスン前提）
    if user_type in ('student', 'teacher'):
        identity = user_type
    else:
        identity = uuid.uuid4().hex[:8]

    logger.info(f"Generating token for identity: {identity}")

    token = twilio.jwt.access_token.AccessToken(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_SECRET,
        identity=identity,
        ttl=3600,
    )
    token.add_grant(twilio.jwt.access_token.grants.VideoGrant(room=room_name))
    return token, identity


@login_required
def video_lesson(request):
    """ビデオチャットページを表示"""
    return render(request, 'video_chat/video_lesson.html')


@login_required_json
@require_http_methods(["POST"])
def make_token(request):
    """Twilio トークンを生成する API"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    room_name = data.get('room_name')
    user_type = data.get('user_type')

    if not room_name or not user_type:
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    if not isinstance(room_name, str) or not room_name.isalnum():
        return JsonResponse({'error': 'Room name must be alphanumeric'}, status=400)
    if user_type not in ('student', 'teacher'):
        return JsonResponse({'error': 'Invalid user type'}, status=400)
    if twilio_client is None:
        return JsonResponse({'error': 'Video service is not configured'}, status=503)

    # 連打対策の短期キャッシュ。他のユーザーとトークンを共有しないよう user を含める
    cache_key = f'room_token_{request.user.pk}_{room_name}_{user_type}'
    cached_data = cache.get(cache_key)
    if cached_data:
        return JsonResponse(cached_data)

    try:
        room = RoomManager(twilio_client).get_or_create_room(room_name)
        token, identity = get_access_token(room_name, user_type=user_type)
        jwt = token.to_jwt()
        response_data = {
            'token': jwt.decode('utf-8') if isinstance(jwt, bytes) else jwt,
            'room': {'name': room_name, 'sid': room.sid, 'status': room.status},
            'identity': identity,
        }
        cache.set(cache_key, response_data, timeout=60)
        return JsonResponse(response_data)

    except Exception:
        logger.exception("Error in make_token")
        return JsonResponse({'error': 'Failed to create video room'}, status=500)


def get_room_recordings(room_sid):
    """部屋の最新の音声録音を取得し、署名付き URL を付けて返す"""
    logger.info(f"Starting get_room_recordings for room_sid: {room_sid}")

    cache_key = f'room_recordings_{room_sid}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    if not twilio_client:
        raise RuntimeError("Twilio client is not initialized")

    recordings = []
    for attempt in range(3):
        recordings = twilio_client.video.recordings.list(grouping_sid=room_sid, status='completed')
        if recordings:
            logger.info(f"Found {len(recordings)} recordings on attempt {attempt + 1}")
            break
        logger.info(f"No recordings found on attempt {attempt + 1}, waiting...")
        time.sleep(5)

    audio_recordings = [r for r in recordings if r.type == 'audio']
    if not audio_recordings:
        logger.warning("No audio recordings found")
        return []

    latest_recording = max(audio_recordings, key=lambda r: r.date_created)
    signed_url = get_signed_url(latest_recording.links['media'])
    if not signed_url:
        logger.error(f"Failed to get signed URL for recording {latest_recording.sid}")
        return []

    media_files = [{
        'url': signed_url,
        'duration': latest_recording.duration or 0,
        'sid': latest_recording.sid,
        'type': 'audio',
        'status': latest_recording.status,
        'created_at': latest_recording.date_created.isoformat(),
    }]
    cache.set(cache_key, media_files, timeout=ROOM_RECORDINGS_CACHE_TIMEOUT)
    return media_files


def get_signed_url(media_url, max_retries=3):
    """Twilio のメディア URL から署名付き URL を取得する"""
    for attempt in range(max_retries):
        try:
            response = requests.get(
                media_url,
                auth=(settings.TWILIO_API_KEY_SID, settings.TWILIO_API_SECRET),
                timeout=30 + (attempt * 10),
                allow_redirects=True,
            )
            response.raise_for_status()
            return response.url
        except requests.RequestException as e:
            logger.error(f"Attempt {attempt + 1} to get signed URL failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(attempt + 1)
    return None


@login_required_json
@require_http_methods(["POST"])
def handle_recording_complete(request):
    """レッスン終了後にブラウザから呼ばれ、最新の録音を保存して文字起こしする"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    room_sid = data.get("RoomSid")
    if not room_sid:
        return JsonResponse({"error": "RoomSid is required"}, status=400)

    try:
        media_files = get_room_recordings(room_sid)
        if not media_files:
            # 202 を返してフロントエンドにリトライさせる
            return JsonResponse({
                "status": "warning",
                "message": "No media files found",
                "room_sid": room_sid,
            }, status=202)

        latest_audio = media_files[0]
        recording = RecordingService().handle_new_recording(
            room_sid=room_sid,
            audio_url=latest_audio['url'],
            duration=latest_audio['duration'],
            user=request.user,
        )

        return JsonResponse({
            "status": "success",
            "recording_id": recording.id,
            "room_sid": room_sid,
            "transcript": recording.transcript or None,
        })

    except Exception:
        logger.exception("Error in handle_recording_complete")
        return JsonResponse({"error": "Failed to process recording"}, status=500)


@login_required_json
@require_http_methods(["GET"])
def recording_status(request, recording_id):
    """録音の状態を確認するエンドポイント"""
    status = RecordingService().get_recording_status(recording_id, user=request.user)
    if status is None:
        return JsonResponse({"error": "Recording not found"}, status=404)
    return JsonResponse(status)


@login_required
@require_http_methods(["GET"])
def recording_list(request):
    """ユーザーの録音一覧を表示"""
    recordings = Recording.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'video_chat/recording_list.html', {'recordings': recordings})


@login_required
@require_http_methods(["GET"])
def player_view(request):
    room_sid = request.GET.get('room_sid')
    if not room_sid:
        return render(request, 'video_chat/player.html', {'error_message': 'Room SID is required'})

    recording = Recording.objects.filter(room_sid=room_sid, user=request.user).first()
    if not recording:
        logger.warning(f"No recording found for room_sid: {room_sid}")
        return render(request, 'video_chat/player.html', {'error_message': 'Recording not found'})

    try:
        media_files = get_room_recordings(room_sid)
    except Exception:
        logger.exception("Error in player_view")
        return render(request, 'video_chat/player.html', {'error_message': 'Failed to load recordings'})

    if not media_files:
        return render(request, 'video_chat/player.html', {'error_message': 'No recordings found for this room'})

    media_file = media_files[0]
    data_array = [{
        'url': media_file['url'],
        'duration': media_file['duration'],
        'created_at': media_file['created_at'],
        'recording_id': recording.id,
        'type': media_file['type'],
    }]

    return render(request, 'video_chat/player.html', {
        'recordings_json': json.dumps(data_array),
        # URL パラメータではなく、保存済みの文字起こしを使う
        'transcript': recording.transcript,
        'recording_id': recording.id,
    })


@login_required_json
@require_http_methods(["POST"])
def go_transcribe(request):
    """（旧フロー）ルームの最新録音をダウンロードして文字起こしし、MEDIA に保存する"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)

    room_sid = data.get("RoomSid")
    if not room_sid:
        return JsonResponse({"error": "RoomSid is required"}, status=400)

    try:
        media_files = get_room_recordings(room_sid)
    except Exception:
        logger.exception("Error fetching recordings")
        return JsonResponse({"error": "Failed to fetch recordings"}, status=500)

    audio_files = [f for f in media_files if f['type'] == 'audio']
    if not audio_files:
        return JsonResponse({"error": "No audio recordings found for this room"}, status=404)

    latest_audio = audio_files[0]
    sid = latest_audio['sid']
    if not RECORDING_SID_RE.match(sid):
        logger.error(f"Unexpected recording SID format: {sid!r}")
        return JsonResponse({"error": "Invalid recording"}, status=500)

    recordings_dir = os.path.join(settings.MEDIA_ROOT, 'recordings')
    os.makedirs(recordings_dir, exist_ok=True)
    original_path = os.path.join(recordings_dir, f"{sid}_original.wav")
    converted_path = os.path.join(recordings_dir, f"{sid}.wav")
    transcript_path = os.path.join(recordings_dir, f"{sid}.txt")

    try:
        response = requests.get(latest_audio['url'], stream=True, timeout=60)
        response.raise_for_status()
        with open(original_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # モノラルの WAV に変換
        AudioSegment.from_file(original_path).export(converted_path, format='wav', parameters=["-ac", "1"])

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        with open(converted_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )

        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write(transcript)

    except Exception:
        logger.exception("Error processing audio")
        return JsonResponse({"error": "Failed to process audio"}, status=500)
    finally:
        if os.path.exists(original_path):
            os.remove(original_path)

    # このユーザーが閲覧してよい文字起こしとしてセッションに記録する
    allowed = request.session.get(TRANSCRIBED_SIDS_SESSION_KEY, [])
    if sid not in allowed:
        request.session[TRANSCRIBED_SIDS_SESSION_KEY] = allowed + [sid]

    return JsonResponse({
        "status": "success",
        "sid": sid,
        "room_sid": room_sid,
        "transcript": transcript,
        "duration": latest_audio['duration'],
    })


@login_required
@require_http_methods(["GET"])
def transcribe_audio(request):
    """（旧フロー）go_transcribe で保存した文字起こしを表示する"""
    sid = request.GET.get('sid', '')

    # パストラバーサル対策: 形式を検証し、自分が文字起こししたものだけを許可する
    if not RECORDING_SID_RE.match(sid) or sid not in request.session.get(TRANSCRIBED_SIDS_SESSION_KEY, []):
        raise Http404("Transcript not found")

    transcript_file_path = os.path.join(settings.MEDIA_ROOT, 'recordings', f"{sid}.txt")
    try:
        with open(transcript_file_path, 'r', encoding='utf-8') as f:
            transcript = f.read()
    except FileNotFoundError:
        raise Http404("Transcript not found")

    return render(request, 'video_chat/transcribe.html', {
        'sid': sid,
        'audio_url': f"{settings.MEDIA_URL}recordings/{sid}.wav",
        'transcript_url': f"{settings.MEDIA_URL}recordings/{sid}.txt",
        'transcript': transcript,
    })
