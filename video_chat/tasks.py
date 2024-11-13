# video_chat/tasks.py
from celery import shared_task
from django.conf import settings
import logging
from .models import Recording
from .services import AudioTranscriptionService

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_recording(self, recording_id):
    """録音の処理を行うCeleryタスク"""
    try:
        recording = Recording.objects.get(id=recording_id)
        
        # AudioTranscriptionServiceを初期化
        transcription_service = AudioTranscriptionService()
        
        # 文字起こし処理
        transcript = transcription_service.transcribe_audio(recording.audio_url)
        recording.transcript = transcript
        recording.mark_as_transcribed()
        
        # 分析タスクを開始
        analyze_recording.delay(recording_id)
        
    except Recording.DoesNotExist:
        logger.error(f"Recording {recording_id} not found")
    except Exception as e:
        logger.error(f"Error processing recording {recording_id}: {e}")
        try:
            recording.mark_as_failed(str(e))
        except:
            pass
        # リトライ回数が残っている場合は再試行
        raise self.retry(exc=e, countdown=60)  # 1分後に再試行

@shared_task(bind=True)
def analyze_recording(self, recording_id):
    """録音の分析を行うCeleryタスク"""
    from conversation_analysis.services import ConversationAnalysisService
    
    try:
        recording = Recording.objects.get(id=recording_id)
        
        if not recording.transcript:
            logger.error(f"No transcript available for recording {recording_id}")
            return
        
        # 分析サービスを初期化
        analysis_service = ConversationAnalysisService()
        
        # 分析を実行
        analysis_service.analyze_recording(recording)
        
        # 状態を更新
        recording.mark_as_analyzed()
        
    except Recording.DoesNotExist:
        logger.error(f"Recording {recording_id} not found")
    except Exception as e:
        logger.error(f"Error analyzing recording {recording_id}: {e}")
        recording.mark_as_failed(str(e))
        raise