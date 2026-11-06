
import logging
import os
import tempfile
import uuid
from datetime import datetime

import requests
from django.conf import settings
from django.core.files import File
from openai import OpenAI
from pydub import AudioSegment

from .models import Recording

logger = logging.getLogger(__name__)

class AudioTranscriptionService:
    def __init__(self):
        self._openai_client = None
        self.recordings_dir = os.path.join(settings.MEDIA_ROOT, 'recordings')
        os.makedirs(self.recordings_dir, exist_ok=True)

    @property
    def openai_client(self):
        # 状態確認など OpenAI を使わない処理では API キーを要求しないよう、必要になってから作る
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

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
        response = requests.get(audio_url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def _convert_audio(self, input_path, output_path):
        """音声ファイルを変換"""
        audio = AudioSegment.from_file(input_path)
        audio.export(output_path, format='wav', parameters=["-ac", "1"])

    def transcribe_file(self, audio_path):
        """ローカルの音声ファイル（変換済みの WAV）を文字起こしする"""
        return self._perform_transcription(audio_path)

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

    def get_recording_status(self, recording_id, user):
        """録音の状態を取得（他のユーザーの録音は見つからない扱いにする）"""
        try:
            recording = Recording.objects.get(id=recording_id, user=user)
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


class InvalidSoloRecording(ValueError):
    """アップロードされた音声が一人用レッスンの録音として使えない"""


class SoloRecordingService:
    """一人用レッスン: ブラウザで録音した音声を保存して文字起こしする"""

    SAMPLE_RATE = 16000  # Whisper と発音分析で使うサンプリングレート
    MAX_REFERENCE_TEXT_LENGTH = 1000

    def __init__(self, transcription_service=None):
        self.transcription_service = transcription_service or AudioTranscriptionService()

    def create_recording(self, user, uploaded_file, topic='', reference_text=''):
        """アップロードされた音声を WAV に変換して保存し、文字起こしまで行う。

        reference_text（音読モードで読んだ文）がある場合は、その文を正解として発音を評価するので
        文字起こし（外部 API）は行わない。
        音声として読めない・短すぎる・長すぎる場合は InvalidSoloRecording を送出する。
        文字起こしに失敗した場合は録音を failed にして例外をそのまま送出する。
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, 'upload')
            with open(source_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)

            try:
                audio = AudioSegment.from_file(source_path)
            except Exception as e:
                raise InvalidSoloRecording('The uploaded file is not a readable audio file.') from e

            duration = len(audio) / 1000
            if duration < settings.SOLO_MIN_RECORDING_SECONDS:
                raise InvalidSoloRecording('The recording is too short.')
            if duration > settings.SOLO_MAX_RECORDING_SECONDS + 5:  # 停止ボタンの遅れ分の余裕
                raise InvalidSoloRecording('The recording is too long.')

            wav_path = os.path.join(tmp_dir, 'recording.wav')
            audio.set_channels(1).set_frame_rate(self.SAMPLE_RATE).export(wav_path, format='wav')

            solo_id = uuid.uuid4().hex
            recording = Recording(
                lesson_type=Recording.LESSON_TYPE_SOLO,
                room_sid=f'{Recording.SOLO_ROOM_SID_PREFIX}{solo_id}',
                duration=round(duration),
                user=user,
                topic=topic[:Recording._meta.get_field('topic').max_length],
                reference_text=reference_text[:self.MAX_REFERENCE_TEXT_LENGTH],
                status='pending',
            )
            with open(wav_path, 'rb') as f:
                recording.audio_file.save(f'{solo_id}.wav', File(f), save=False)
            recording.save()

            if recording.is_read_aloud:
                recording.mark_as_transcribed()  # 正解の文が分かっているので、すぐに評価できる
                return recording

            try:
                recording.transcript = self.transcription_service.transcribe_file(wav_path)
            except Exception as e:
                logger.error(f"Solo transcription failed: {e}")
                recording.mark_as_failed(str(e))
                raise
            recording.mark_as_transcribed()
            return recording
