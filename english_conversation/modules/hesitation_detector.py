
from collections import deque
from typing import List, Dict, Set, Optional
import numpy as np
import re
import time

class HesitationDetector:
    def __init__(self):
        # 基本設定
        self.speech_buffer = deque(maxlen=50)  # 直近の発話履歴
        
        # フィラーワードのセット（英語）
        self.filler_words = {
            'basic': {'um', 'uh', 'er', 'ah', 'like', 'you know', 'well'},
            'thinking': {'let me see', 'let me think', 'how should i say'},
            'correction': {'i mean', 'what i mean is', 'actually'},
            'japanese_english': {'ano', 'eto', 'nanka'}  # 日本人英語学習者特有
        }
        
        # 文末表現パターン
        self.sentence_enders = {'.', '?', '!'}
        
        # 分析用メトリクス
        self.metrics = {
            'filler_count': 0,
            'repetitions': 0,
            'incomplete_sentences': 0,
            'silence_intervals': [],
            'speech_rate': 0.0,
            'confidence_score': 1.0
        }
        
        # 分析用の閾値
        self.thresholds = {
            'high_filler_rate': 0.2,    # フィラー率の閾値
            'high_repetition_rate': 0.15,  # 繰り返し率の閾値
            'min_confidence': 0.4,      # 最小信頼度
            'speech_rate_range': (100, 160)  # 適正な発話速度範囲（語/分）
        }

    def analyze_speech(self, text: str, audio_info: Dict = None) -> Dict:
        """
        発話を分析して躊躇パターンを検出

        Parameters:
        - text: 分析する発話テキスト
        - audio_info: 音声関連の情報（オプション）

        Returns:
        - Dict: 分析結果
        """
        # テキストの前処理
        processed_text = self._preprocess_text(text)
        words = processed_text.split()
        
        # 各種分析の実行
        filler_analysis = self._analyze_fillers(words)
        repetition_analysis = self._analyze_repetitions(words)
        completion_analysis = self._analyze_sentence_completion(text)
        speech_rate = self._calculate_speech_rate(words, audio_info)
        
        # 信頼度スコアの計算
        confidence_score = self._calculate_confidence_score(
            filler_analysis,
            repetition_analysis,
            completion_analysis,
            speech_rate
        )

        # 履歴の更新
        self._update_history(text, confidence_score)

        return {
            'hesitation_detected': confidence_score < self.thresholds['min_confidence'],
            'confidence_score': confidence_score,
            'analysis': {
                'fillers': filler_analysis,
                'repetitions': repetition_analysis,
                'completion': completion_analysis,
                'speech_rate': speech_rate
            },
            'suggestions': self._generate_suggestions(
                filler_analysis,
                repetition_analysis,
                completion_analysis
            )
        }

    def _preprocess_text(self, text: str) -> str:
        """テキストの前処理"""
        # 小文字化
        text = text.lower()
        # 不要な空白の削除
        text = ' '.join(text.split())
        # 基本的な正規化
        text = re.sub(r'[^\w\s.?!]', '', text)
        return text

    def _analyze_fillers(self, words: List[str]) -> Dict:
        """フィラーワードの分析"""
        filler_counts = {
            category: sum(1 for word in words if word in filler_set)
            for category, filler_set in self.filler_words.items()
        }
        
        total_fillers = sum(filler_counts.values())
        filler_rate = total_fillers / len(words) if words else 0
        
        return {
            'total_count': total_fillers,
            'rate': filler_rate,
            'by_category': filler_counts,
            'is_high': filler_rate > self.thresholds['high_filler_rate']
        }

    def _analyze_repetitions(self, words: List[str]) -> Dict:
        """単語の繰り返しパターンを分析"""
        repetitions = []
        repetition_count = 0
        
        for i in range(len(words) - 1):
            if words[i] == words[i + 1]:
                repetition_count += 1
                repetitions.append(words[i])
                
        repetition_rate = repetition_count / len(words) if words else 0
        
        return {
            'count': repetition_count,
            'rate': repetition_rate,
            'repeated_words': repetitions,
            'is_high': repetition_rate > self.thresholds['high_repetition_rate']
        }

    def _analyze_sentence_completion(self, text: str) -> Dict:
        """文の完成度を分析"""
        sentences = [s.strip() for s in re.split('[.!?]', text) if s.strip()]
        incomplete_count = 0
        incomplete_sentences = []
        
        for sentence in sentences:
            if not self._is_complete_sentence(sentence):
                incomplete_count += 1
                incomplete_sentences.append(sentence)
                
        return {
            'complete_count': len(sentences) - incomplete_count,
            'incomplete_count': incomplete_count,
            'incomplete_sentences': incomplete_sentences,
            'completion_rate': (len(sentences) - incomplete_count) / len(sentences) if sentences else 0
        }

    def _calculate_speech_rate(self, words: List[str], audio_info: Optional[Dict]) -> float:
        """発話速度の計算"""
        if not audio_info or 'duration' not in audio_info:
            return 0.0
            
        words_per_minute = (len(words) / audio_info['duration']) * 60
        return words_per_minute

    def _calculate_confidence_score(self, 
                                  filler_analysis: Dict,
                                  repetition_analysis: Dict,
                                  completion_analysis: Dict,
                                  speech_rate: float) -> float:
        """信頼度スコアの計算"""
        # 各要素のウェイト
        weights = {
            'filler': 0.3,
            'repetition': 0.25,
            'completion': 0.25,
            'speech_rate': 0.2
        }
        
        # 各要素のスコア計算
        filler_score = 1.0 - min(1.0, filler_analysis['rate'] * 2)
        repetition_score = 1.0 - min(1.0, repetition_analysis['rate'] * 2)
        completion_score = completion_analysis['completion_rate']
        
        # 発話速度のスコア
        min_rate, max_rate = self.thresholds['speech_rate_range']
        speech_rate_score = 1.0
        if speech_rate < min_rate:
            speech_rate_score = speech_rate / min_rate
        elif speech_rate > max_rate:
            speech_rate_score = max_rate / speech_rate
            
        # 総合スコアの計算
        total_score = (
            weights['filler'] * filler_score +
            weights['repetition'] * repetition_score +
            weights['completion'] * completion_score +
            weights['speech_rate'] * speech_rate_score
        )
        
        return max(0.0, min(1.0, total_score))

    def _generate_suggestions(self,
                            filler_analysis: Dict,
                            repetition_analysis: Dict,
                            completion_analysis: Dict) -> List[str]:
        """改善提案の生成"""
        suggestions = []
        
        # フィラー対策の提案
        if filler_analysis['is_high']:
            suggestions.append(
                "Try using transitional phrases instead of fillers: "
                "'In my opinion...', 'To be specific...'"
            )
            
        # 繰り返し対策の提案
        if repetition_analysis['is_high']:
            suggestions.append(
                "Take a brief pause to organize your thoughts "
                "instead of repeating words."
            )
            
        # 文完成度の改善提案
        if completion_analysis['incomplete_count'] > 0:
            suggestions.append(
                "Try to complete your sentences. "
                "You can practice using simple sentence structures first."
            )
            
        return suggestions

    def _is_complete_sentence(self, sentence: str) -> bool:
        """文が完全かどうかを判定"""
        # 基本的な文構造のチェック
        has_subject = bool(re.search(r'\b(i|you|he|she|it|we|they)\b', sentence.lower()))
        has_verb = bool(re.search(r'\b(is|am|are|was|were|have|has|had|do|does|did|go|goes|went)\b', sentence.lower()))
        
        return has_subject and has_verb

    def _update_history(self, text: str, confidence_score: float) -> None:
        """発話履歴の更新"""
        self.speech_buffer.append({
            'text': text,
            'confidence_score': confidence_score,
            'timestamp': time.time()
        })
