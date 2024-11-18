import nltk
from nltk.tokenize import word_tokenize
from collections import Counter
from typing import List, Dict

class VocabularyDiversityAnalyzer:
    def __init__(self):
        nltk.download('punkt_tab')
        """語彙多様性分析クラスの初期化"""
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
    
    def preprocess_text(self, text: str) -> List[str]:
        """テキストの前処理を行う"""
        text = text.lower()
        tokens = word_tokenize(text)
        tokens = [token for token in tokens if token.isalpha()]
        return tokens
    
    def calculate_mtld(self, tokens: List[str], factor_size: float = 0.72) -> float:
        """MLTDスコアを計算
        
        Args:
            tokens: 単語のリスト
            factor_size: 因子サイズ（デフォルト0.72）
            
        Returns:
            MLTDスコア
        """
        if not tokens:
            return 0.0
        
        def mtld_forward(tokens: List[str]) -> float:
            factors = 0
            factor_count = 0
            current_ttr = 1.0
            start = 0
            
            for i in range(len(tokens)):
                factor_count += 1
                current_ttr = len(set(tokens[start:i+1])) / factor_count
                
                if current_ttr <= factor_size:
                    factors += 1
                    start = i + 1
                    factor_count = 0
                    current_ttr = 1.0
            
            if factor_count > 0:
                factors += (1 - current_ttr) / (1 - factor_size)
            
            return len(tokens) / factors if factors > 0 else len(tokens)
        
        forward = mtld_forward(tokens)
        backward = mtld_forward(tokens[::-1])
        return (forward + backward) / 2
    
    def analyze_text(self, text: str) -> Dict:
        """テキストの語彙多様性を分析
        
        Args:
            text: 分析対象のテキスト
            
        Returns:
            {'mtld': MLTDスコア, 'token_count': 総単語数, 'top_words': 頻出単語}
        """
        tokens = self.preprocess_text(text)
        
        results = {
            'mtld': self.calculate_mtld(tokens)
        }
        
        return results