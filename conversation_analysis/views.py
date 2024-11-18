# conversation_analysis/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from .services import ConversationAnalysisService
from .models import ConversationAnalysis, WordFrequency, POSDistribution
from video_chat.models import Recording
import logging
from .synonym_service import SynonymSuggestionService
from .service_audio import PronunciationAnalysisSystem
from django.views.decorators.csrf import csrf_exempt
import os
from django.conf import settings

logger = logging.getLogger(__name__)


openai_api_key = settings.OPENAI_API_KEY


@login_required
def analysis_detail(request, recording_id):
    """会話分析の詳細を表示"""
    recording = get_object_or_404(Recording, id=recording_id, user=request.user)
    
    try:
        # 分析サービスのインスタンスを作成
        analysis_service = ConversationAnalysisService()
       
        
        try:
            # 既存の分析を取得
            analysis = ConversationAnalysis.objects.get(recording=recording)
            if not analysis.is_completed:
                # 完了していない分析は再実行
                analysis = analysis_service.analyze_recording(recording)
        except ConversationAnalysis.DoesNotExist:
            # 分析が存在しない場合は新規作成
            logger.info(f"Creating new analysis for recording {recording_id}")
            analysis = analysis_service.analyze_recording(recording)
        

        

        # データの準備
        freq_dict = dict(WordFrequency.objects.filter(
            analysis=analysis
        ).order_by('-count')[:5].values_list('word', 'count'))
        
        count_word = []
        for pos in set(WordFrequency.objects.filter(
            analysis=analysis
        ).values_list('pos_tag', flat=True)):
            words = WordFrequency.objects.filter(
                analysis=analysis,
                pos_tag=pos
            ).order_by('-count')
            count_word.append((pos, dict(words.values_list('word', 'count'))))

        top5_ranking = WordFrequency.objects.filter(
            analysis=analysis
        ).order_by('-count')[:5].values_list('word', 'count')

        ranking_by_pos = []
        for pos in set(WordFrequency.objects.filter(
            analysis=analysis
        ).values_list('pos_tag', flat=True)):
            pos_words = WordFrequency.objects.filter(
                analysis=analysis,
                pos_tag=pos
            ).order_by('-count')[:3]
            if pos_words:
                ranking_by_pos.append((pos, pos_words.values_list('word', 'count')))

        mltd_score = analysis.mltd_score

        room_sid = recording.room_sid
        transcript = recording.transcript

        context = {
            
            'room_sid':room_sid,
            'transcript':transcript,
            'analysis': analysis,
            'freq_dict': freq_dict,
            'count_word': count_word,
            'top5_ranking': top5_ranking,
            'ranking_by_pos': ranking_by_pos,
            'mltd_score':mltd_score,
        }

        synonym_service = SynonymSuggestionService()

        synonym_suggestions = synonym_service.get_suggestions_for_ranking(
            WordFrequency.objects.filter(analysis=analysis)
        )

        context['synonym_suggestions'] = synonym_suggestions


        
        return render(request, 'conversation_analysis/analysis.html', context)
        
    except Exception as e:
        logger.error(f"Error in analysis_detail: {str(e)}")
        logger.exception("Full traceback:")  # 詳細なエラー情報をログに記録
        return JsonResponse({
            'error': 'Failed to analyze recording',
            'details': str(e)
        }, status=500)
    
def audio_analysis(request):
    room_sid = request.GET.get('room_sid')  
    transcript = request.GET.get('transcript')
    return render(request, 'conversation_analysis/audio_analysis.html', {
        'room_sid': room_sid,
        'transcript': transcript
    })

@csrf_exempt
def generate_audio(request):
    if request.method == 'POST':
        room_sid = request.POST.get('room_sid')
        transcript = request.POST.get('transcript')
        try:
            system = PronunciationAnalysisSystem(openai_api_key)
            audio_path = system.generate_reference_audio(transcript)
            audio_path_recorded = system.get_room_recording(room_sid)

            return JsonResponse({
                'audio_path': audio_path,
                'audio_path_recorded': audio_path_recorded
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

def get_audio_file(request, filename):
    file_path = os.path.join('temp_audio', filename)
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='audio/wav')
            return response
    return HttpResponse(status=404)