# conversation_analysis/views.py
import logging
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
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
    """ログインユーザー自身の録音だけを返す（他人の room_sid なら 404）"""
    if not room_sid:
        raise Http404("Recording not found")
    recording = Recording.objects.filter(room_sid=room_sid, user=request.user).first()
    if recording is None or not recording.transcript:
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
        'room_sid': recording.room_sid,
        'transcript': recording.transcript,
    })


def _local_audio_path(recording):
    """一人用レッスンならサーバーに保存した録音のパス、ルームレッスンなら None（Twilio から取得）"""
    if recording.is_solo and recording.audio_file:
        return recording.audio_file.path
    return None


def _pronunciation_system():
    from .service_audio import PronunciationAnalysisSystem  # librosa などの重い依存を遅延読み込み

    return PronunciationAnalysisSystem(settings.OPENAI_API_KEY)


@login_required_json
@require_POST
def generate_audio(request):
    try:
        recording = _get_user_recording(request, request.POST.get('room_sid'))
    except Http404:
        return JsonResponse({'error': 'Recording not found'}, status=404)

    try:
        system = _pronunciation_system()
        audio_path = system.generate_reference_audio(recording.transcript)
        audio_path_recorded = system.get_room_recording(
            recording.room_sid, local_audio_path=_local_audio_path(recording))
    except Exception:
        logger.exception("Error in generate_audio")
        return JsonResponse({'error': 'Failed to prepare audio'}, status=500)

    _allow_audio_files(request, audio_path, audio_path_recorded)
    return JsonResponse({
        'audio_path': Path(audio_path).name,
        'audio_path_recorded': Path(audio_path_recorded).name,
    })


@login_required_json
@require_POST
def analyze_pronunciation(request):
    try:
        recording = _get_user_recording(request, request.POST.get('room_sid'))
    except Http404:
        return JsonResponse({'error': 'Recording not found'}, status=404)

    try:
        logger.info(f"Starting pronunciation analysis for room {recording.room_sid}")
        result = _pronunciation_system().analyze_pronunciation(
            recording.room_sid, recording.transcript, local_audio_path=_local_audio_path(recording))
    except Exception:
        logger.exception("Error in analyze_pronunciation")
        return JsonResponse({'error': 'Failed to analyze pronunciation'}, status=500)

    word_comparisons = [
        {
            'word': comp['word'],
            'difference_score': float(comp['difference_score']),
            'similarity': float(comp['similarity']),
            'start_time': float(comp['start_time']),
            'end_time': float(comp['end_time']),
            'duration_difference': float(comp['duration_difference']),
        }
        for comp in result['word_comparisons']
    ]
    word_comparisons.sort(key=lambda x: x['difference_score'], reverse=True)

    audio_paths = result['audio_paths']
    _allow_audio_files(request, *audio_paths.values())

    return JsonResponse({
        'score': float(result['score']),
        'total_words': len(word_comparisons),
        'word_comparisons': word_comparisons,
        'sentence_boundaries': result['sentence_boundaries'],
        'audio_paths': {key: Path(path).name for key, path in audio_paths.items()},
    })


@login_required
def get_audio_file(request, filename):
    # このセッションで生成したファイル名のみ許可（パストラバーサル・他人の録音の取得を防ぐ）
    if filename != Path(filename).name or filename not in request.session.get(AUDIO_FILES_SESSION_KEY, []):
        raise Http404("Audio not found")

    file_path = Path(settings.TEMP_AUDIO_DIR) / filename
    if not file_path.is_file():
        raise Http404("Audio not found")
    return FileResponse(open(file_path, 'rb'), content_type='audio/wav')


def calculate_speaking_rate(word_comparisons):
    """単語/分の発話速度を計算"""
    if not word_comparisons:
        return 0

    total_duration = calculate_total_duration(word_comparisons)
    if total_duration > 0:
        return round((len(word_comparisons) / total_duration) * 60, 1)
    return 0


def calculate_total_duration(word_comparisons):
    """総発話時間を計算（秒）"""
    if not word_comparisons:
        return 0

    last_word = max(word_comparisons, key=lambda x: x['end_time'])
    first_word = min(word_comparisons, key=lambda x: x['start_time'])
    return round(last_word['end_time'] - first_word['start_time'], 1)
