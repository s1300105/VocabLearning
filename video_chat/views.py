import os
import uuid
import logging
import json
import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, csrf_protect, get_token
from django.views.decorators.http import require_http_methods
from django.conf import settings
import twilio.jwt.access_token
import twilio.jwt.access_token.grants
import twilio.rest
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseRedirect
from datetime import datetime, timedelta
from django.urls import reverse
from django.contrib import messages
from django.shortcuts import redirect
from celery import shared_task
import speech_recognition as sr
from pydub import AudioSegment
from textblob import TextBlob
import os
from pydub.utils import which
import tempfile
import time
#import whisper
from openai import OpenAI
from moviepy.editor import VideoFileClip
from django.core.cache import cache
from django.core.cache import cache
from django.db import transaction
import time




class RoomManager:
    def __init__(self, twilio_client):
        self.twilio_client = twilio_client
        self.lock_timeout = 30

    def _cleanup_existing_room(self, room_name):
        """既存のルームをクリーンアップする"""
        try:
            # まず既存のルームを探す
            rooms = self.twilio_client.video.rooms.list(unique_name=room_name, status='in-progress')
            
            for room in rooms:
                try:
                    logger.info(f"Completing room: {room.sid}")
                    # ルームを完了状態に更新
                    self.twilio_client.video.rooms(room.sid).update(status='completed')
                    # キャッシュをクリア
                    cache.delete(f'room_{room_name}')
                    cache.delete(f'recording_rules_{room.sid}')
                    # 完了を待機
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error completing room {room.sid}: {str(e)}")

            # 完了後、さらに待機してTwilioのシステムに変更が反映されるのを待つ
            time.sleep(3)
            
        except Exception as e:
            logger.error(f"Error in cleanup: {str(e)}")
            # クリーンアップの失敗は致命的ではないので、例外は発生させない

    def get_or_create_room(self, room_name, max_retries=3, delay=1):
        """ロックを使用して部屋を取得または作成"""
        # まず既存のアクティブなルームを確認
        try:
            existing_room = self.twilio_client.video.rooms(room_name).fetch()
            if existing_room.status != 'completed':
                logger.info(f"Found active room: {room_name}")
                # 録音ルールを確認・設定
                self._ensure_recording_rules(existing_room.sid)
                return existing_room
        except TwilioRestException as e:
            if e.code != 20404:  # Room not found以外のエラー
                logger.error(f"Unexpected Twilio error: {str(e)}")
            # Room not foundの場合は続行

        lock_key = f'room_lock_{room_name}'
        last_error = None
        
        for attempt in range(max_retries):
            if cache.add(lock_key, True, self.lock_timeout):
                try:
                    # 既存のルームをクリーンアップ
                    self._cleanup_existing_room(room_name)

                    # 新しいルーム作成を試みる
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

        # すべての試行が失敗した場合は、最後にもう一度ルーム作成を試みる
        logger.warning(f"Failed to acquire lock, attempting final room creation: {room_name}")
        try:
            return self._create_new_room(room_name)
        except Exception as e:
            last_error = e
            logger.error(f"Final room creation attempt failed: {str(e)}")

        if last_error:
            raise last_error
        raise Exception("Failed to create or acquire room")

    def _create_new_room(self, room_name):
        """新しいルームを作成する"""
        for create_attempt in range(3):
            try:
                room = self.twilio_client.video.rooms.create(
                    unique_name=room_name,
                    type="group",
                    record_participants_on_connect=True,
                    status_callback=settings.TWILIO_STATUS_CALLBACK_URL,
                    video_codecs=['VP8', 'H264']
                )
                
                logger.info(f"Created new room: {room_name} (SID: {room.sid})")
                
                # 録音ルールを設定
                self._set_recording_rules(room.sid)
                
                # キャッシュを更新
                cache.set(f'room_{room_name}', {
                    'sid': room.sid,
                    'status': room.status
                }, timeout=3600)
                
                return room
                
            except TwilioRestException as e:
                if e.code == 53113:  # Room exists エラー
                    logger.warning(f"Room still exists, retrying after cleanup (attempt {create_attempt + 1})")
                    time.sleep(2)
                    continue
                raise
                
        return None

    def _set_recording_rules(self, room_sid):
        """録音ルールを設定する"""
        rules = [
            {
                'type': "include",
                'kind': "audio",
                'publisher': "student"
            }
        ]
        
        try:
            # ルールを設定する前に少し待機
            time.sleep(1)
            
            # ルールを更新
            self.twilio_client.video.rooms(room_sid).recording_rules.update(rules=rules)
            
            # 更新後のルールを確認
            updated_rules = self.twilio_client.video.rooms(room_sid).recording_rules.fetch()
            if updated_rules and updated_rules.rules:
                logger.info(f"Successfully set recording rules for room: {room_sid}")
                # キャッシュにルールを保存
                cache.set(f'recording_rules_{room_sid}', rules, timeout=3600)
            else:
                raise Exception("Failed to verify recording rules")
                
        except Exception as e:
            logger.error(f"Error setting recording rules: {str(e)}")
            raise

    def _ensure_recording_rules(self, room_sid):
        """録音ルールが設定されているか確認し、必要に応じて設定する"""
        try:
            # キャッシュされたルールを確認
            cached_rules = cache.get(f'recording_rules_{room_sid}')
            if not cached_rules:
                # キャッシュにない場合は設定を確認して必要なら設定
                current_rules = self.twilio_client.video.rooms(room_sid).recording_rules.fetch()
                if not current_rules or not current_rules.rules:
                    self._set_recording_rules(room_sid)
        except Exception as e:
            logger.error(f"Error ensuring recording rules: {str(e)}")
            # エラーは無視してルームの使用を継続



# アプリケーション固有のロガーを取得
logger = logging.getLogger('video_chat')

# Twilioクライアントの初期化
try:
    twilio_client = twilio.rest.Client(
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_SECRET,
        settings.TWILIO_ACCOUNT_SID
    )
except Exception as e:
    logger.error(f"Failed to initialize Twilio client: {str(e)}")
    twilio_client = None




def find_or_create_room(room_name):
    """既存のルームを探すか、新しいルームを作成する"""
    if not twilio_client:
        logger.error("Twilio client is not initialized")
        raise Exception("Twilio client is not initialized")
    
    def set_recording_rules(room_sid):
        """録音ルールを設定する補助関数"""
        try:
            logger.info(f"Setting recording rules for room {room_sid}")
            
            Rules = [
                {
                    'type': "include",
                    'kind': "audio",
                    'publisher': "student"
                }
            ]
            
            # キャッシュキーを作成
            cache_key = f'recording_rules_{room_sid}'
            
            # 既存のルールをチェック
            existing_rules = cache.get(cache_key)
            if existing_rules == Rules:
                logger.info("Recording rules already set correctly")
                return True
                
            # ルールを更新
            result = twilio_client.video.rooms(room_sid).recording_rules.update(rules=Rules)
            
            # 新しいルールをキャッシュ
            cache.set(cache_key, Rules, timeout=3600)
            
            return True
                
        except Exception as e:
            logger.error(f"Failed to set recording rules: {str(e)}")
            return False

    try:
        logger.info(f"Finding or creating room: {room_name}")

        # キャッシュキーを作成
        room_cache_key = f'room_{room_name}'
        
        # キャッシュされたルーム情報を確認
        cached_room = cache.get(room_cache_key)
        if cached_room:
            try:
                # キャッシュされたルームが有効か確認
                room = twilio_client.video.rooms(cached_room['sid']).fetch()
                if room.status == 'completed':
                    cache.delete(room_cache_key)
                else:
                    return room
            except Exception:
                cache.delete(room_cache_key)

        try:
            # 既存のルームを探す
            room = twilio_client.video.rooms(room_name).fetch()
            
            # ルームが完了状態の場合は新しいルームを作成
            if room.status == 'completed':
                raise TwilioRestException(status=404, message="Room completed")
                
            logger.info(f"Found existing room: {room_name} (SID: {room.sid})")
            
            # ルーム情報をキャッシュ
            cache.set(room_cache_key, {
                'sid': room.sid,
                'status': room.status
            }, timeout=3600)
            
            return room
            
        except TwilioRestException as e:
            if e.status == 404:
                # 新しいルームを作成
                room = twilio_client.video.rooms.create(
                    unique_name=room_name,
                    type="group",
                    record_participants_on_connect=True,
                    status_callback=settings.TWILIO_STATUS_CALLBACK_URL,
                    video_codecs=['VP8', 'H264']
                )
                
                logger.info(f"Created new room: {room_name} (SID: {room.sid})")
                
                # 録音ルールを設定
                if not set_recording_rules(room.sid):
                    logger.warning(f"Failed to set recording rules for new room {room_name}")
                
                # ルーム情報をキャッシュ
                cache.set(room_cache_key, {
                    'sid': room.sid,
                    'status': room.status
                }, timeout=3600)
                
                return room
            else:
                raise
                
    except Exception as e:
        logger.error(f"Error in find_or_create_room: {str(e)}")
        logger.exception("Full traceback:")
        raise




def get_access_token(room_name, identity=None, user_type=None):
    """アクセストークンを生成する"""
    if not all([
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_SECRET
    ]):
        raise ValueError("Twilio credentials are not properly configured")
    
    try:
        # シンプルなidentityの生成（uuidは使用しない）
        if user_type == 'student':
            identity = f"student"  # シンプルに'student'のみ
        elif user_type == 'teacher':
            identity = f"teacher"  # シンプルに'teacher'のみ
        else:
            identity = str(uuid.uuid4().hex[:8])
        
        logger.info(f"Generating token for identity: {identity}")
        
        token = twilio.jwt.access_token.AccessToken(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_API_KEY_SID,
            settings.TWILIO_API_SECRET,
            identity=identity,
            ttl=3600
        )
        
        grant = twilio.jwt.access_token.grants.VideoGrant(room=room_name)
        token.add_grant(grant)
        
        return token, identity
        
    except Exception as e:
        logger.error(f"Failed to generate access token: {str(e)}")
        raise




def video_lesson(request):
    """ビデオチャットページを表示"""
    return render(request, 'video_chat/video_lesson.html')



@csrf_protect
@require_http_methods(["POST"])
def make_token(request):
    """Twilioトークンを生成するAPI"""
    try:
        data = json.loads(request.body)
        room_name = data.get('room_name')
        user_type = data.get('user_type')
        
        if not room_name or not user_type:
            return JsonResponse({
                'error': 'Invalid parameters'
            }, status=400)

        # ルーム名とユーザータイプの検証
        if not room_name.isalnum():
            return JsonResponse({
                'error': 'Room name must be alphanumeric'
            }, status=400)
            
        if user_type not in ['student', 'teacher']:
            return JsonResponse({
                'error': 'Invalid user type'
            }, status=400)

        # キャッシュをチェック
        cache_key = f'room_token_{room_name}_{user_type}'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return JsonResponse(cached_data)

        # 新しいルームを作成または取得
        room_manager = RoomManager(twilio_client)
        
        try:
            room = room_manager.get_or_create_room(room_name)
            token, identity = get_access_token(room_name, user_type=user_type)
            
            response_data = {
                'token': token.to_jwt().decode('utf-8') if isinstance(token.to_jwt(), bytes) else token.to_jwt(),
                'room': {
                    'name': room_name,
                    'sid': room.sid,
                    'status': room.status
                },
                'identity': identity
            }
            
            # レスポンスをキャッシュ（短い時間）
            cache.set(cache_key, response_data, timeout=60)
            
            return JsonResponse(response_data)
            
        except TwilioRestException as e:
            logger.error(f"Twilio error: {str(e)}")
            return JsonResponse({
                'error': str(e)
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error in make_token: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)



def get_room_recordings(room_sid):
    """部屋の録音データを取得"""
    logger.info(f"Starting get_room_recordings for room_sid: {room_sid}")
    
    if not twilio_client:
        logger.error("Twilio client is not initialized")
        raise Exception("Twilio client is not initialized")
    
    try:
        # 現在のセッションの開始時刻を取得
        room = twilio_client.video.rooms(room_sid).fetch()
        session_start = room.date_created
        logger.info(f"Current session started at: {session_start}")

        # 録音を取得
        recordings = twilio_client.video.recordings.list(
            grouping_sid=room_sid,
            status='completed'
        )
        
        # 最新の録音のみを処理
        latest_recording = None
        latest_date = None
        
        for recording in recordings:
            if recording.type == 'audio':
                if latest_date is None or recording.date_created > latest_date:
                    latest_recording = recording
                    latest_date = recording.date_created

        if latest_recording:
            try:
                media_url = latest_recording.links['media']
                logger.debug(f"Processing latest recording {latest_recording.sid}")
                
                signed_url = get_signed_url(media_url)
                
                if signed_url:
                    media_files = [{
                        'url': signed_url,
                        'duration': latest_recording.duration if latest_recording.duration else 0,
                        'sid': latest_recording.sid,
                        'type': 'audio',
                        'status': latest_recording.status,
                        'created_at': latest_recording.date_created.isoformat()
                    }]
                    logger.info(f"Successfully processed latest recording from current session")
                    return media_files
                else:
                    logger.error(f"Failed to get signed URL for recording {latest_recording.sid}")
            except Exception as e:
                logger.error(f"Error processing recording {latest_recording.sid}: {str(e)}")
        
        return []
        
    except Exception as e:
        logger.error(f"Error in get_room_recordings: {str(e)}")
        logger.exception("Full traceback:")
        raise



@csrf_exempt
@require_http_methods(["POST"])
def handle_recording_complete(request):
    """録音完了時のハンドラー"""
    try:
        data = json.loads(request.body)
        room_sid = data.get("RoomSid")
        transcribe_requested = data.get("transcribe", False)
        
        if not room_sid:
            return JsonResponse({"error": "RoomSid is required"}, status=400)
        
        logger.info(f"Handling recording complete for room: {room_sid}")
        
        # 古いキャッシュをクリア
        cache_key = f'room_recordings_{room_sid}'
        cache.delete(cache_key)

        # 録音データが利用可能になるまでの待機
        time.sleep(5)
        
        # 最新の録音データのみを取得
        media_files = get_room_recordings(room_sid)
        
        if not media_files:
            return JsonResponse({
                "status": "warning",
                "message": "No media files found",
                "room_sid": room_sid
            })

        # 最新の録音データのみをキャッシュ
        cache.set(cache_key, media_files, timeout=3600)
        
        # 文字起こしが要求された場合、最新の録音のみを処理
        if transcribe_requested and media_files:
            try:
                latest_audio = media_files[0]  # 最新の録音のみを処理
                audio_url = latest_audio['url']
                
                # 音声ファイルの処理
                recordings_dir = os.path.join(settings.MEDIA_ROOT, 'recordings')
                os.makedirs(recordings_dir, exist_ok=True)
                
                # 一時ファイル名にタイムスタンプを追加して重複を防ぐ
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                original_path = os.path.join(recordings_dir, f"{latest_audio['sid']}_{timestamp}_original.wav")
                converted_path = os.path.join(recordings_dir, f"{latest_audio['sid']}_{timestamp}.wav")
                
                response = requests.get(audio_url, stream=True)
                if response.status_code == 200:
                    with open(original_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                    audio = AudioSegment.from_file(original_path)
                    audio.export(converted_path, format='wav', parameters=["-ac", "1"])
                    
                    # 文字起こし処理
                    OPENAI_API_KEY = settings.OPENAI_API_KEY
                    client = OpenAI(api_key=OPENAI_API_KEY)

                    with open(converted_path, "rb") as audio_file:
                        transcript_response = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            response_format="text"
                        )
                        transcript = transcript_response

                    # 一時ファイルを削除
                    for path in [original_path, converted_path]:
                        if os.path.exists(path):
                            os.remove(path)
                    
                    return JsonResponse({
                        "status": "success",
                        "media_files": media_files,
                        "room_sid": room_sid,
                        "transcript": transcript
                    })
            except Exception as e:
                logger.error(f"Error in transcription: {str(e)}")
                return JsonResponse({
                    "error": f"Transcription failed: {str(e)}"
                }, status=500)

        return JsonResponse({
            "status": "success",
            "message": f"Found {len(media_files)} media files",
            "media_files": media_files,
            "room_sid": room_sid
        })
            
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return JsonResponse({
            "error": "Invalid JSON format in request body"
        }, status=400)
    except Exception as e:
        logger.error(f"Error in handle_recording_complete: {str(e)}")
        return JsonResponse({
            "error": str(e)
        }, status=500)



def get_signed_url(media_url, max_retries=3):
    """TwilioのメディアURLから署名付きURLを取得する"""
    logger.debug(f"Getting signed URL for: {media_url}")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                media_url,
                auth=(settings.TWILIO_API_KEY_SID, settings.TWILIO_API_SECRET),
                timeout=30 + (attempt * 10),
                allow_redirects=True
            )
            response.raise_for_status()
            logger.debug(f"Successfully got signed URL on attempt {attempt + 1}")
            return response.url
            
        except requests.RequestException as e:
            logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                return None
            time.sleep(1 * (attempt + 1))
            
    return None


@require_http_methods(["GET"])  # GETメソッドに変更
def transcribe_audio(request):
    """文字起こしページを表示"""
    sid = request.GET.get('sid')
    if not sid:
        return JsonResponse({"error": "SID is required"}, status=400)
        
    try:
        return render(request, 'video_chat/transcribe.html', {
            'sid': sid
        })
    except Exception as e:
        logger.error(f"Error in transcribe_audio: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)





def analyze_english_speech(transcript):
    """英語の発話を分析"""
    analysis = {
        'text': transcript,
        'word_count': len(transcript.split()),
        'sentiment': None,
        'language_score': None,
        'grammar_errors': []
    }
    
    try:
        blob = TextBlob(transcript)
        
        # 感情分析
        analysis['sentiment'] = blob.sentiment.polarity
        
        # 文法チェック
        grammar_errors = []
        # ここに文法チェックのロジックを追加
        
        analysis['grammar_errors'] = grammar_errors
        
        return analysis
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return analysis



@require_http_methods(["GET"])
def player_view(request):
    """録画プレーヤーページを表示"""
    try:
        room_sid = request.GET.get('room_sid')
        transcript = request.GET.get('transcript')
        
        if not room_sid:
            return render(request, 'video_chat/player.html', {
                'error_message': 'Room SID is required'
            })
        
            # キャッシュから録音データを取得
        media_files = cache.get(f'room_recordings_{room_sid}')
        
        if not media_files:
            # キャッシュになければ再取得
            media_files = get_room_recordings(room_sid)
            
        if media_files:
            media_files.sort(key=lambda x: x['created_at'], reverse=True)
            logger.info(f"Found {len(media_files)} media files for room {room_sid}")
            
            # JSONデータをエスケープせずに渡す
            recordings_json = json.dumps(media_files)
            
            context = {
                'recordings_json': recordings_json,
            }
            
            # transcriptが存在する場合のみcontextに追加
            if transcript:
                context['transcript'] = transcript
            
            return render(request, 'video_chat/player.html', context)
        else:
            return render(request, 'video_chat/player.html', {
                'error_message': 'No recordings found for this room'
            })
                

            
    except Exception as e:
        logger.error(f"Error in player_view: {str(e)}")
        return render(request, 'video_chat/player.html', {
            'error_message': 'Failed to load recordings'
        })




# Whisper モデルで文字起こし
#model = whisper.load_model("base")
#result = model.transcribe(audio_path)
#transcript = result["text"]



@csrf_exempt
@require_http_methods(["POST"])
def go_transcribe(request):
    logger.info("go_transcribe endpoint called")
    try:
        data = json.loads(request.body)
        room_sid = data.get("RoomSid")
        logger.info(f"Processing room_sid: {room_sid}")

        if not room_sid:
            logger.error("No RoomSid provided")
            return JsonResponse({"error": "RoomSid is required"}, status=400)

        try:
            media_files = cache.get(f'room_recordings_{room_sid}')

            if not media_files:
                # キャッシュになければ再取得
                media_files = get_room_recordings(room_sid)
            
            if not media_files:
                logger.warning(f"No recordings found for room {room_sid}")
                return JsonResponse({
                    "error": "No recordings found for this room"
                }, status=404)
            
            # 最新の音声録画を取得
            audio_files = [f for f in media_files if f['type'] == 'audio']
            if not audio_files:
                return JsonResponse({
                    "error": "No audio recordings found for this room"
                }, status=404)
            
            latest_audio = audio_files[0]
            audio_url = latest_audio['url']
            
            try:
                # 音声ファイルをダウンロード
                recordings_dir = os.path.join(settings.MEDIA_ROOT, 'recordings')
                os.makedirs(recordings_dir, exist_ok=True)
                original_path = os.path.join(recordings_dir, f"{latest_audio['sid']}_original.wav")
                converted_path = os.path.join(recordings_dir, f"{latest_audio['sid']}.wav")
                
                response = requests.get(audio_url, stream=True)
                if response.status_code == 200:
                    # オリジナルファイルを保存
                    with open(original_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                    # AudioSegmentを使用してフォーマット変換
                    audio = AudioSegment.from_file(original_path)
                    audio.export(converted_path, format='wav', parameters=["-ac", "1"])  # モノラルのWAVに変換
                    
                    # Whisper APIで文字起こし
                    OPENAI_API_KEY = settings.OPENAI_API_KEY
                    client = OpenAI(api_key=OPENAI_API_KEY)

                    with open(converted_path, "rb") as audio_file:
                        try:
                            response = client.audio.transcriptions.create(
                                model="whisper-1",
                                file=audio_file,
                                response_format="text"
                            )
                            transcript = response
                        except Exception as e:
                            logger.error(f"Transcription error: {str(e)}")
                            return JsonResponse({
                                "error": f"Failed to transcribe audio: {str(e)}"
                            }, status=500)

                    # 文字起こし結果を保存
                    transcript_path = os.path.join(recordings_dir, f"{latest_audio['sid']}.txt")
                    with open(transcript_path, 'w', encoding='utf-8') as f:
                        f.write(transcript)
                    
                    # 一時ファイルを削除
                    if os.path.exists(original_path):
                        os.remove(original_path)
                    
                    return JsonResponse({
                        "status": "success",
                        "sid": latest_audio['sid'],
                        "room_sid": room_sid,
                        "transcript": transcript,
                        "duration": latest_audio['duration']
                    })
                else:
                    raise Exception(f"Failed to download audio: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error processing audio: {str(e)}")
                return JsonResponse({
                    "error": f"Failed to process audio: {str(e)}"
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error fetching recordings: {str(e)}")
            return JsonResponse({
                "error": f"Failed to fetch recordings: {str(e)}"
            }, status=500)
            
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format: {str(e)}")
        return JsonResponse({
            "error": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Internal server error: {str(e)}")
        return JsonResponse({
            "error": f"Internal server error: {str(e)}"
        }, status=500)

    


@require_http_methods(["GET"])
def transcribe_audio(request):
    sid = request.GET.get('sid')
    
    if not sid:
        return JsonResponse({"error": "SID is required"}, status=400)
    
    try:
        # 保存されたファイルのパスを構築
        recordings_dir = os.path.join(settings.MEDIA_ROOT, 'recordings')
        video_path = os.path.join('recordings', f"{sid}.mp4")
        transcript_path = os.path.join('recordings', f"{sid}.txt")
        
        # 文字起こしテキストを読み込む
        transcript_file_path = os.path.join(settings.MEDIA_ROOT, transcript_path)
        with open(transcript_file_path, 'r', encoding='utf-8') as f:
            transcript = f.read()
        
        return render(request, 'video_chat/transcribe.html', {
            'sid': sid,
            'video_url': f"/media/{video_path}",
            'transcript_url': f"/media/{transcript_path}",
            'transcript': transcript
        })
        
    except Exception as e:
        logger.error(f"Error in transcribe_audio: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)