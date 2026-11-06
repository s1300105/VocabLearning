# conversation_analysis/views.py
import logging
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from video_chat.decorators import login_required_json
from video_chat.models import Recording

from .models import ConversationAnalysis, WordFrequency
from .services import ConversationAnalysisService
from .synonym_service import SynonymSuggestionService

logger = logging.getLogger(__name__)

# get_audio_file で配信してよいファイル名（このセッションで生成したもの）
AUDIO_FILES_SESSION_KEY = 'pronunciation_audio_files'


def _get_user_recording(request, room_sid):
    """ログインユーザー自身の、発音チェックできる録音だけを返す（他人の room_sid なら 404）"""
    if not room_sid:
        raise Http404("Recording not found")
    recording = Recording.objects.filter(room_sid=room_sid, user=request.user).first()
    if recording is None or not recording.pronunciation_text:
        raise Http404("Recording not found")
    return recording


def _allow_audio_files(request, *paths):
    allowed = set(request.session.get(AUDIO_FILES_SESSION_KEY, []))
    allowed.update(Path(p).name for p in paths if p)
    request.session[AUDIO_FILES_SESSION_KEY] = sorted(allowed)


@login_required
def analysis_detail(request, recording_id):
    """会話分析の詳細を表示"""
    recording = get_object_or_404(Recording, id=recording_id, user=request.user)

    try:
        analysis = ConversationAnalysis.objects.filter(recording=recording, is_completed=True).first()
        if analysis is None:
            logger.info(f"Creating analysis for recording {recording_id}")
            analysis = ConversationAnalysisService().analyze_recording(recording)

        word_frequencies = WordFrequency.objects.filter(analysis=analysis)
        all_words = list(word_frequencies.order_by('-count').values_list('word', 'count', 'pos_tag'))

        top5_ranking = [(word, count) for word, count, _ in all_words[:5]]

        words_by_pos = defaultdict(list)
        for word, count, pos in all_words:
            words_by_pos[pos].append((word, count))

        context = {
            'room_sid': recording.room_sid,
            'transcript': recording.transcript,
            'analysis': analysis,
            'freq_dict': dict(top5_ranking),
            'count_word': [(pos, dict(words)) for pos, words in words_by_pos.items()],
            'top5_ranking': top5_ranking,
            'ranking_by_pos': [(pos, words[:3]) for pos, words in words_by_pos.items()],
            'mltd_score': analysis.mltd_score,
            'synonym_suggestions': SynonymSuggestionService().get_suggestions_for_ranking(word_frequencies),
        }
        return render(request, 'conversation_analysis/analysis.html', context)

    except Exception:
        logger.exception("Error in analysis_detail")
        return JsonResponse({'error': 'Failed to analyze recording'}, status=500)


@login_required
def audio_analysis(request):
    recording = _get_user_recording(request, request.GET.get('room_sid'))
    return render(request, 'conversation_analysis/audio_analysis.html', {
        'recording': recording,
        'room_sid': recording.room_sid,
        'text': recording.pronunciation_text,
        'is_read_aloud': recording.is_read_aloud,
    })


def _local_audio_path(recording):
    """一人用レッスンならサーバーに保存した録音のパス、ルームレッスンなら None（Twilio から取得）"""
    if recording.is_solo and recording.audio_file:
        return recording.audio_file.path
    return None


def _audio_service():
    from .service_audio import PronunciationAnalysisSystem

    return PronunciationAnalysisSystem(settings.OPENAI_API_KEY)


def _audio_url(filename):
    return reverse('conversation_analysis:get_audio_file', args=[filename])


@login_required_json
@require_POST
def analyze_pronunciation(request):
    """学習者の録音を、ローカルの音素認識モデルで音素ごとに採点する（外部 API は使わない）"""
    try:
        recording = _get_user_recording(request, request.POST.get('room_sid'))
    except Http404:
        return JsonResponse({'error': 'Recording not found'}, status=404)

    try:
        from .pronunciation.assessor import get_assessor
    except ImportError:
        logger.exception("Pronunciation model dependencies are missing")
        return JsonResponse({'error': 'The pronunciation model is not installed on the server'}, status=503)

    try:
        learner_path = _audio_service().get_room_recording(
            recording.room_sid, local_audio_path=_local_audio_path(recording))
        result = get_assessor().assess_file(learner_path, recording.pronunciation_text)
    except ValueError as e:
        # 録音が短すぎて文と対応付けられない、評価できる単語がない、など
        logger.warning(f"Pronunciation analysis rejected: {e}")
        return JsonResponse({'error': 'Could not match your recording with the text. '
                                      'Please record the whole sentence again.'}, status=400)
    except Exception:
        logger.exception("Error in analyze_pronunciation")
        return JsonResponse({'error': 'Failed to analyze pronunciation'}, status=500)

    _allow_audio_files(request, learner_path)
    result['learner_audio_url'] = _audio_url(Path(learner_path).name)
    return JsonResponse(result)


@login_required_json
@require_POST
def generate_audio(request):
    """お手本の音声（OpenAI TTS）を作る。聞き比べ用で、採点には使わない"""
    try:
        recording = _get_user_recording(request, request.POST.get('room_sid'))
    except Http404:
        return JsonResponse({'error': 'Recording not found'}, status=404)
    if not settings.OPENAI_API_KEY:
        return JsonResponse({'error': 'Model voice is not available'}, status=503)

    try:
        audio_path = _audio_service().generate_reference_audio(recording.pronunciation_text)
    except Exception:
        logger.exception("Error in generate_audio")
        return JsonResponse({'error': 'Failed to prepare the model voice'}, status=500)

    _allow_audio_files(request, audio_path)
    return JsonResponse({'model_audio_url': _audio_url(Path(audio_path).name)})


@login_required
def get_audio_file(request, filename):
    # このセッションで生成したファイル名のみ許可（パストラバーサル・他人の録音の取得を防ぐ）
    if filename != Path(filename).name or filename not in request.session.get(AUDIO_FILES_SESSION_KEY, []):
        raise Http404("Audio not found")

    file_path = Path(settings.TEMP_AUDIO_DIR) / filename
    if not file_path.is_file():
        raise Http404("Audio not found")
    return FileResponse(open(file_path, 'rb'), content_type='audio/wav')
