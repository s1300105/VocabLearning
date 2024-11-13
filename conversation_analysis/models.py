# conversation_analysis/models.py
from django.db import models
from video_chat.models import Recording

class ConversationAnalysis(models.Model):
    recording = models.OneToOneField(Recording, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    word_count = models.IntegerField(default=0)
    is_completed = models.BooleanField(default=False)

    # 分析結果のJSONフィールド
    word_frequency = models.JSONField(default=dict)  # 単語頻度
    pos_analysis = models.JSONField(default=dict)    # 品詞分析
    grammar_score = models.FloatField(null=True)     # 文法スコア
    
    def __str__(self):
        return f"Analysis for recording {self.recording.id}"

class WordFrequency(models.Model):
    analysis = models.ForeignKey(ConversationAnalysis, on_delete=models.CASCADE)
    word = models.CharField(max_length=100)
    count = models.IntegerField()
    pos_tag = models.CharField(max_length=20)  # 品詞タグ
    lemma = models.CharField(max_length=100)   # 基本形

    class Meta:
        ordering = ['-count']
        verbose_name_plural = "Word frequencies"

class POSDistribution(models.Model):
    """品詞の分布分析"""
    analysis = models.ForeignKey(ConversationAnalysis, on_delete=models.CASCADE)
    pos_tag = models.CharField(max_length=20)  # 品詞タグ
    count = models.IntegerField()
    percentage = models.FloatField()

    class Meta:
        ordering = ['-count']