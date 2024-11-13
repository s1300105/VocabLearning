# conversation_analysis/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .services import ConversationAnalysisService
from .models import ConversationAnalysis, WordFrequency, POSDistribution
from video_chat.models import Recording
import logging
from .synonym_service import SynonymSuggestionService

logger = logging.getLogger(__name__)


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

        context = {
            'recording': recording,
            'analysis': analysis,
            'freq_dict': freq_dict,
            'count_word': count_word,
            'top5_ranking': top5_ranking,
            'ranking_by_pos': ranking_by_pos
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