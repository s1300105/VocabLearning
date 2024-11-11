import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from collections import Counter
from nltk.probability import FreqDist
import spacy
from typing import Dict, List, Tuple
import pandas as pd
from collections import Counter


class WordFrequencyAnalyzer:
  def __init__(self):
    nltk.download('stopwords')
    self.nlp = spacy.load("en_core_web_sm")
    self.stop_words = set(stopwords.words("english"))

  def analyze_text(self, text: str) -> Dict:
    doc = self.nlp(text)

    #基本的な単語のカウント　アルファベットかつストップワードではない
    word_counts = Counter([
        token.text.lower() 
        for token in doc 
        if token.is_alpha and token.text.lower() not in self.stop_words
    ])

    #品詞別に単語をカウント
    pos_counts = {}
    for token in doc:
      if token.pos_ not in pos_counts:
        pos_counts[token.pos_] = Counter()
      if token.is_alpha:
        pos_counts[token.pos_][token.text.lower()] += 1

    word_df = pd.DataFrame([
        {
            'word':word,
            'count':count,
            'pos': [token.pos_ for token in doc if token.text.lower() == word][0],
            'lemma': [token.lemma_ for token in doc if token.text.lower() == word][0]
        }
        for word, count in word_counts.most_common()
    ])

    return {
        'word_counts': word_counts,
        'pos_counts': pos_counts,
        'word_df': word_df
    }
  
  def generate_rankings(self, analysis_results: Dict) -> Dict:
    rankings = {
        'overall' : analysis_results['word_counts'].most_common(),
        'by_pos': {
            pos: counts.most_common()
            for pos, counts in analysis_results['pos_counts'].items()
        }
    }

    return rankings

  def export_to_excel(self, rankings: Dict, filename: str):
        with pd.ExcelWriter(filename) as writer:
            # 全体ランキング
            pd.DataFrame(rankings['overall'], 
                        columns=['Word', 'Count']).to_excel(writer, 
                                                          sheet_name='Overall Ranking')
            
            # 品詞別ランキング
            for pos, rank in rankings['by_pos'].items():
                pd.DataFrame(rank, 
                           columns=['Word', 'Count']).to_excel(writer, 
                                                             sheet_name=f'{pos} Ranking')


