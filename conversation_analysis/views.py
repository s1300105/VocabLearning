from django.shortcuts import render
from .analysis import WordFrequencyAnalyzer
from collections import Counter
# Create your views here.

# views.py
def word_freq(request):
    transcribe_text = """
    I think this project is really important for our company. 
    The team has been working hard to achieve our goals.
    We need to focus on improving the quality of our products.
    I believe we can make significant progress if we continue working together.
    The customers are happy with our service, but we should always strive to do better.
    """

    analyzer = WordFrequencyAnalyzer()
    analysis_results = analyzer.analyze_text(transcribe_text)
    rankings = analyzer.generate_rankings(analysis_results)

    # 上位5単語とその頻度（グラフ用にデータを整形）
    freq_dict = dict(analysis_results['word_counts'].most_common(5))
    
    # 品詞別カウントデータ（品詞ごとの単語出現回数）
    count_word = [
        (pos, dict(counts.most_common()))  # 全ての単語を含める
        for pos, counts in analysis_results['pos_counts'].items()
    ]
    
    # 全体ランキング（上位5件）
    top5_ranking = rankings['overall'][:5]
    
    # 品詞別ランキング（各品詞上位3件）
    ranking_by_pos = [
        (pos, rank[:3])
        for pos, rank in rankings['by_pos'].items()
        if rank  # 空のランキングを除外
    ]

    context = {
        'freq_dict': freq_dict,
        'count_word': count_word,
        'top5_ranking': top5_ranking,
        'ranking_by_pos': ranking_by_pos,

    }
    
    return render(request, "conversation_analysis/analysis.html", context)