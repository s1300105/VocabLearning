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
from pathlib import Path


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


@csrf_exempt
def analyze_pronunciation(request):
    if request.method == 'POST':
        room_sid = request.POST.get('room_sid')
        transcript = request.POST.get('transcript')
        try:
            logger.info(f"Starting pronunciation analysis for room {room_sid}")
            system = PronunciationAnalysisSystem(openai_api_key)
            
            result = system.analyze_pronunciation(room_sid, transcript)
            
            # 音声ファイルのパスを保存
            response_data = {
                'score': float(result['score']),
                'total_words': len(result['word_comparisons']),
                'word_comparisons': [],
                'audio_paths': result['audio_paths']  # 追加
            }
            
            for comp in result['word_comparisons']:
                word_data = {
                    'word': comp['word'],
                    'difference_score': float(comp['difference_score']),
                    'start_time': float(comp['start_time']),
                    'end_time': float(comp['end_time']),
                    'duration_difference': float(comp['duration_difference'])
                }
                response_data['word_comparisons'].append(word_data)
            
            response_data['word_comparisons'].sort(key=lambda x: x['difference_score'], reverse=True)
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"Error in analyze_pronunciation: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)




def get_audio_file(request, filename):
    try:
        file_path = os.path.join(settings.BASE_DIR, 'temp_audio', filename)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='audio/wav')
                return response
    except Exception as e:
        logger.error(f"Error serving audio file: {e}")
    return HttpResponse(status=404)



def calculate_speaking_rate(word_comparisons):
    """単語/分の発話速度を計算"""
    if not word_comparisons:
        return 0
    
    total_duration = calculate_total_duration(word_comparisons)
    word_count = len(word_comparisons)
    
    # 分あたりの単語数を計算
    if total_duration > 0:
        return round((word_count / total_duration) * 60, 1)
    return 0

def calculate_total_duration(word_comparisons):
    """総発話時間を計算（秒）"""
    if not word_comparisons:
        return 0
    
    last_word = max(word_comparisons, key=lambda x: x['end_time'])
    first_word = min(word_comparisons, key=lambda x: x['start_time'])
    
    return round(last_word['end_time'] - first_word['start_time'], 1)