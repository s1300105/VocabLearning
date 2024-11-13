# conversation_analysis/synonym_service.py
from nltk.corpus import wordnet
from collections import defaultdict
import nltk
import logging

logger = logging.getLogger(__name__)

class SynonymSuggestionService:
    """WordNetを使用して類似語を提案するサービス"""
    
    def __init__(self):
        try:
            nltk.data.find('corpora/wordnet')
        except LookupError:
            nltk.download('wordnet')
    
    def get_synonyms(self, word, pos_tag):
        """
        指定された単語と品詞の類似語を取得
        
        Args:
            word (str): 対象の単語
            pos_tag (str): spaCyの品詞タグ
            
        Returns:
            list: 類似語のリスト（最大5個）
        """
        # spaCyの品詞タグをWordNetの品詞タグに変換
        pos_map = {
            'NOUN': wordnet.NOUN,
            'VERB': wordnet.VERB,
            'ADJ': wordnet.ADJ,
            'ADV': wordnet.ADV
        }
        
        wn_pos = pos_map.get(pos_tag)
        if not wn_pos:
            return []
            
        synonyms = set()
        for synset in wordnet.synsets(word, pos=wn_pos):
            for lemma in synset.lemmas():
                synonym = lemma.name()
                if synonym != word and '_' not in synonym:  # 元の単語と複合語を除外
                    synonyms.add(synonym)
                    if len(synonyms) >= 5:  # 最大5つまで
                        break
            if len(synonyms) >= 5:
                break
                
        return list(synonyms)
    
    def get_suggestions_for_ranking(self, word_frequencies, start_rank=5, end_rank=10):
        """
        指定された順位範囲の単語に対して類似語を提案
        
        Args:
            word_frequencies (QuerySet): WordFrequencyモデルのクエリセット
            start_rank (int): 開始順位（デフォルト: 5）
            end_rank (int): 終了順位（デフォルト: 10）
            
        Returns:
            dict: 品詞ごとの類似語提案
        """
        suggestions = defaultdict(list)
        
        # 対象とする品詞
        target_pos = ['NOUN', 'VERB']
        
        for pos in target_pos:
            # 指定された品詞の単語を頻度順に取得
            words = word_frequencies.filter(
                pos_tag=pos
            ).order_by('-count')[start_rank-1:end_rank]
            
            # 各単語に対して類似語を取得
            for word_freq in words:
                synonyms = self.get_synonyms(word_freq.word, pos)
                if synonyms:
                    suggestions[pos].append({
                        'word': word_freq.word,
                        'count': word_freq.count,
                        'rank': list(word_frequencies.filter(
                            pos_tag=pos
                        ).order_by('-count')).index(word_freq) + 1,
                        'synonyms': synonyms
                    })
                    
        return dict(suggestions)