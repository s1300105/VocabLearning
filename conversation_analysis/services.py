# conversation_analysis/services.py
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from collections import Counter
import spacy
import pandas as pd
from .models import ConversationAnalysis, WordFrequency, POSDistribution
import logging
from .vocab_diversity_analysis import VocabularyDiversityAnalyzer

logger = logging.getLogger(__name__)

class ConversationAnalysisService:
    def __init__(self):
        nltk.download('stopwords')
        self.nlp = spacy.load("en_core_web_sm")
        self.stop_words = set(stopwords.words("english"))

    def analyze_recording(self, recording):
      """録音の文字起こしを分析"""
      try:
          logger.info(f"Starting analysis for recording {recording.id}")
          
          # 分析インスタンスを取得または作成
          analysis, created = ConversationAnalysis.objects.get_or_create(
              recording=recording,
              defaults={'word_count': 0}
          )
          
          if not recording.transcript:
              raise ValueError("No transcript available for analysis")

          # テキストの分析を実行
          analysis_results = self.analyze_text(recording.transcript)
          
          # 分析結果を保存
          analysis.word_count = len(analysis_results['word_counts'])
          analysis.word_frequency = dict(analysis_results['word_counts'].most_common(20))
          analysis.pos_analysis = {
              pos: dict(counts.most_common(5))
              for pos, counts in analysis_results['pos_counts'].items()
          }
          analysis.mltd_score = analysis_results['mtld']
          analysis.is_completed = True
          analysis.save()

          logger.info(f"Saving word frequencies for analysis {analysis.id}")
          # 単語頻度の保存
          self._save_word_frequencies(analysis, analysis_results['word_df'])
          
          logger.info(f"Saving POS distribution for analysis {analysis.id}")
          # 品詞分布の保存
          self._save_pos_distribution(analysis, analysis_results['pos_counts'])

          logger.info(f"Analysis completed successfully for recording {recording.id}")
          return analysis

      except Exception as e:
          logger.error(f"Error analyzing recording {recording.id}: {e}")
          logger.exception("Full traceback:")
          raise

    def analyze_text(self, text):
        """テキストの分析を実行"""
        doc = self.nlp(text)

        # 基本的な単語のカウント
        word_counts = Counter([
            token.text.lower() 
            for token in doc 
            if token.is_alpha and token.text.lower() not in self.stop_words
        ])

        # 品詞別に単語をカウント
        pos_counts = {}
        for token in doc:
            if token.pos_ not in pos_counts:
                pos_counts[token.pos_] = Counter()
            if token.is_alpha:
                pos_counts[token.pos_][token.text.lower()] += 1
        
        diversity_analyzer = VocabularyDiversityAnalyzer()
        diversity = diversity_analyzer.analyze_text(text)

        # 単語情報のDataFrame作成
        word_df = pd.DataFrame([
            {
                'word': word,
                'count': count,
                'pos': [token.pos_ for token in doc if token.text.lower() == word][0],
                'lemma': [token.lemma_ for token in doc if token.text.lower() == word][0]
            }
            for word, count in word_counts.most_common()
        ])

        return {
            'word_counts': word_counts,
            'pos_counts': pos_counts,
            'word_df': word_df,
            'mtld':diversity["mtld"]
        }

    def _save_word_frequencies(self, analysis, word_df):
        """単語頻度情報を保存"""
        # 既存のデータを削除
        WordFrequency.objects.filter(analysis=analysis).delete()
        
        # 新しいデータを作成
        word_freqs = []
        for _, row in word_df.iterrows():
            word_freqs.append(WordFrequency(
                analysis=analysis,
                word=row['word'],
                count=row['count'],
                pos_tag=row['pos'],
                lemma=row['lemma']
            ))
        
        # バルク作成
        WordFrequency.objects.bulk_create(word_freqs)

    def _save_pos_distribution(self, analysis, pos_counts):
        """品詞分布情報を保存"""
        # 既存のデータを削除
        POSDistribution.objects.filter(analysis=analysis).delete()
        
        # 総単語数を計算
        total_words = sum(sum(counts.values()) for counts in pos_counts.values())
        
        # 新しいデータを作成
        pos_distributions = []
        for pos, counts in pos_counts.items():
            total_pos = sum(counts.values())
            pos_distributions.append(POSDistribution(
                analysis=analysis,
                pos_tag=pos,
                count=total_pos,
                percentage=(total_pos / total_words * 100 if total_words > 0 else 0)
            ))
        
        # バルク作成
        POSDistribution.objects.bulk_create(pos_distributions)

    def get_analysis_summary(self, analysis_id):
        """分析結果のサマリーを取得"""
        try:
            analysis = ConversationAnalysis.objects.get(id=analysis_id)
            
            return {
                'word_count': analysis.word_count,
                'top_words': dict(WordFrequency.objects.filter(
                    analysis=analysis
                ).order_by('-count')[:10].values_list('word', 'count')),
                'pos_distribution': list(POSDistribution.objects.filter(
                    analysis=analysis
                ).values('pos_tag', 'count', 'percentage')),
                'word_frequency': analysis.word_frequency
            }
        except ConversationAnalysis.DoesNotExist:
            return None