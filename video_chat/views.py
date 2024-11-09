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




# ロガーの設定
logger = logging.getLogger(__name__)

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
        raise Exception("Twilio client is not initialized")
        
    try:
        room = twilio_client.video.rooms(room_name).fetch()
        logger.info(f"Found existing room: {room_name}")
        return room
    except TwilioRestException as e:
        if e.code == 20404:  # Room not found
            try:
                room = twilio_client.video.rooms.create(
                    unique_name=room_name,
                    type="group",
                    record_participants_on_connect=True,
                    status_callback=settings.TWILIO_STATUS_CALLBACK_URL,  # コールバックURLを追加
                    video_codecs=['VP8', 'H264']  # ビデオコーデックを指定
                )
                logger.info(f"Created new room: {room_name}")

                Rules = [
                    {'type':"include", "kind":"audio"}
                ]
                twilio_client.video.rooms(room.sid).recording_rules.update(rules=Rules)

                return room
            except TwilioRestException as create_error:
                logger.error(f"Failed to create room: {str(create_error)}")
                raise
        raise

def get_access_token(room_name, identity=None):
    """アクセストークンを生成する"""
    if not all([
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_SECRET
    ]):
        raise ValueError("Twilio credentials are not properly configured")
        
    if identity is None:
        identity = str(uuid.uuid4().int)
    
    try:
        token = twilio.jwt.access_token.AccessToken(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_API_KEY_SID,
            settings.TWILIO_API_SECRET,
            identity=identity,
            ttl=3600  # 1時間
        )
        
        grant = twilio.jwt.access_token.grants.VideoGrant(room=room_name)
        token.add_grant(grant)
        
        logger.debug(f"Generated access token for identity: {identity}")
        return token
        
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
        
        if not room_name:
            return JsonResponse({'error': 'Room name is required'}, status=400)
            
        if not room_name.isalnum():
            return JsonResponse({'error': 'Room name must be alphanumeric'}, status=400)
            
        # ルームの作成または取得
        room = find_or_create_room(room_name)
        
        # トークンの生成
        token = get_access_token(room_name)
        
        # JWT トークンの生成と変換
        jwt_token = token.to_jwt()
        if isinstance(jwt_token, bytes):
            jwt_token = jwt_token.decode('utf-8')
            
        return JsonResponse({
            'token': jwt_token,
            'room': {
                'name': room_name,
                'sid': room.sid,
                'status': room.status
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON data'
        }, status=400)
        
    except Exception as e:
        logger.error(f"Error in generate_token: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error',
            'details': str(e)
        }, status=500)



def get_room_recordings(room_sid):
    """部屋の録音データを取得"""
    logger.info(f"Starting get_room_recordings for room_sid: {room_sid}")
    
    if not twilio_client:
        logger.error("Twilio client is not initialized")
        raise Exception("Twilio client is not initialized")
    
    try:
        # まず全ての録音を取得
        recordings = twilio_client.video.recordings.list(
            grouping_sid=room_sid
        )
        
        logger.info(f"Found {len(recordings)} total recordings for room {room_sid}")
        
        # 音声データのURLを取得
        media_files = []
        for recording in recordings:
            try:
                # 処理中のステータスをログ
                logger.debug(f"Recording {recording.sid} status: {recording.status}")
                
                # 録音が完了していない場合はスキップ
                if recording.status != 'completed':
                    logger.debug(f"Skipping recording {recording.sid} with status {recording.status}")
                    continue

                # 音声録音のみを処理
                if recording.type == 'audio':
                    try:
                        media_url = recording.links['media']
                        logger.debug(f"Got media URL for recording {recording.sid}")
                        
                        signed_url = get_signed_url(media_url)
                        
                        if signed_url:
                            media_files.append({
                                'url': signed_url,
                                'duration': recording.duration if recording.duration else 0,
                                'sid': recording.sid,
                                'type': 'audio',
                                'status': recording.status,
                                'created_at': recording.date_created.isoformat()
                            })
                            logger.debug(f"Successfully added media file for recording {recording.sid}")
                        else:
                            logger.error(f"Failed to get signed URL for recording {recording.sid}")
                    except AttributeError as e:
                        logger.error(f"Missing attribute for recording {recording.sid}: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error getting media URL for recording {recording.sid}: {str(e)}")
            except Exception as e:
                logger.error(f"Error processing recording {recording.sid}: {str(e)}")
        
        logger.info(f"Successfully processed {len(media_files)} audio files")
        return media_files
        
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
        
        if not room_sid:
            return JsonResponse({"error": "RoomSid is required"}, status=400)
        
        logger.info(f"Handling recording complete for room: {room_sid}")
        
        # 録音データが利用可能になるまでの待機時間を延長
        time.sleep(5)
        
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                media_files = get_room_recordings(room_sid)
                
                if media_files:
                    response_data = {
                        "status": "success",
                        "message": f"Found {len(media_files)} media files",
                        "media_files": media_files,
                        "room_sid": room_sid
                    }
                    logger.info(f"Successfully processed room {room_sid} with {len(media_files)} media files")
                    return JsonResponse(response_data)
                else:
                    if attempt < max_retries - 1:
                        logger.warning(f"No media files found on attempt {attempt + 1}, retrying...")
                        time.sleep(retry_delay)
                        continue
                    
                    return JsonResponse({
                        "status": "warning",
                        "message": "No media files found",
                        "room_sid": room_sid
                    })
                    
            except Exception as e:
                logger.error(f"Error on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                raise
                
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
    for attempt in range(max_retries):
        try:
            response = requests.get(
                media_url,
                auth=(settings.TWILIO_API_KEY_SID, settings.TWILIO_API_SECRET),
                timeout=30 + (attempt * 10),
                allow_redirects=True
            )
            response.raise_for_status()
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
        
        try:
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
            logger.error(f"Error getting recordings for room {room_sid}: {str(e)}")
            return render(request, 'video_chat/player.html', {
                'error_message': 'Failed to load recordings'
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