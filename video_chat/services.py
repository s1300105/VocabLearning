
from django.conf import settings
import requests
import os
from datetime import datetime
from pydub import AudioSegment
from openai import OpenAI
import logging
from .models import Recording

logger = logging.getLogger(__name__)

class AudioTranscriptionService:
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.recordings_dir = os.path.join(settings.MEDIA_ROOT, 'recordings')
        os.makedirs(self.recordings_dir, exist_ok=True)

    def transcribe_audio(self, audio_url):
        """音声ファイルの文字起こしを行う"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        original_path = os.path.join(self.recordings_dir, f"temp_{timestamp}_original.wav")
        converted_path = os.path.join(self.recordings_dir, f"temp_{timestamp}.wav")
        
        try:
            # 音声ファイルをダウンロード
            self._download_audio(audio_url, original_path)
            
            # 音声ファイルを変換
            self._convert_audio(original_path, converted_path)
            
            # 文字起こしを実行
            return self._perform_transcription(converted_path)
            
        finally:
            # 一時ファイルを削除
            self._cleanup_files([original_path, converted_path])


    def _download_audio(self, audio_url, save_path):
        """音声ファイルをダウンロード"""
        response = requests.get(audio_url, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def _convert_audio(self, input_path, output_path):
        """音声ファイルを変換"""
        audio = AudioSegment.from_file(input_path)
        audio.export(output_path, format='wav', parameters=["-ac", "1"])

    def _perform_transcription(self, audio_path):
        """WhisperAPIを使用して文字起こしを実行"""
        with open(audio_path, "rb") as audio_file:
            transcript_response = self.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
            return transcript_response

    def _cleanup_files(self, file_paths):
        """一時ファイルを削除"""
        for path in file_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Failed to delete file {path}: {e}")



class RecordingService:
    def __init__(self):
        self.transcription_service = AudioTranscriptionService()

    def create_recording(self, room_sid, audio_url, duration, user):
        """新しい録音レコードを作成"""
        try:
            # 録音レコードを作成
            recording = Recording.objects.create(
                room_sid=room_sid,
                audio_url=audio_url,
                duration=duration,
                user=user,
                status='pending'
            )
            
            # 同期的に文字起こしを実行
            try:
                transcript = self.transcription_service.transcribe_audio(audio_url)
                recording.transcript = transcript
                recording.status = 'transcribed'
                recording.save()
                
                return recording
                
            except Exception as e:
                logger.error(f"Transcription failed: {e}")
                recording.mark_as_failed(str(e))
                raise
            
        except Exception as e:
            logger.error(f"Error creating recording: {e}")
            raise

    def handle_new_recording(self, room_sid, audio_url, duration, user):
        """新しい録音を処理"""
        try:
            recording = self.create_recording(
                room_sid=room_sid,
                audio_url=audio_url,
                duration=duration,
                user=user
            )
            
            return recording
            
        except Exception as e:
            logger.error(f"Error handling new recording: {e}")
            raise

    def get_recording_status(self, recording_id):
        """録音の状態を取得"""
        try:
            recording = Recording.objects.get(id=recording_id)
            return {
                'status': recording.status,
                'transcript': recording.transcript if recording.transcript else None,
                'is_analyzed': recording.is_analyzed,
                'error': recording.error_message if recording.error_message else None
            }
        except Recording.DoesNotExist:
            return None

    def list_user_recordings(self, user):
        """ユーザーの録音一覧を取得"""
        return Recording.objects.filter(user=user).order_by('-created_at')