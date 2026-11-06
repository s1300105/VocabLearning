from django.conf import settings
from django.db import models

from .storage import PrivateMediaStorage

class Recording(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('transcribed', 'Transcribed'),
        ('analyzed', 'Analyzed'),
        ('failed', 'Failed')
    ]
    
    LESSON_TYPE_ROOM = 'room'
    LESSON_TYPE_SOLO = 'solo'
    LESSON_TYPE_CHOICES = [
        (LESSON_TYPE_ROOM, 'Room lesson'),
        (LESSON_TYPE_SOLO, 'Solo practice'),
    ]
    # 一人用レッスンの録音は Twilio のルームがないので、"SOLO" + ランダムな ID を入れる
    SOLO_ROOM_SID_PREFIX = 'SOLO'

    lesson_type = models.CharField(max_length=10, choices=LESSON_TYPE_CHOICES, default=LESSON_TYPE_ROOM)
    room_sid = models.CharField(max_length=255)
    audio_url = models.URLField(max_length=500, blank=True)  # Twilio の録音 URL（ルームレッスンのみ）
    # 一人用レッスンの録音（16kHz モノラル WAV）。公開ディレクトリには置かない
    audio_file = models.FileField(upload_to='solo_recordings/%Y/%m/', storage=PrivateMediaStorage(), blank=True)
    topic = models.CharField(max_length=300, blank=True)
    # 音読モードで読み上げた文。発音評価はこの文を正解として行う（空なら文字起こしを使う）
    reference_text = models.TextField(blank=True)
    duration = models.IntegerField()  # 秒単位
    transcript = models.TextField(null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_analyzed = models.BooleanField(default=False)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['room_sid']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status'])
        ]

    def __str__(self):
        return f"Recording {self.room_sid} - {self.created_at}"

    @property
    def is_solo(self):
        return self.lesson_type == self.LESSON_TYPE_SOLO

    @property
    def is_read_aloud(self):
        return bool(self.reference_text)

    @property
    def pronunciation_text(self):
        """発音評価で「正しく言うべき文」として使う文"""
        return self.reference_text or self.transcript or ''

    def mark_as_failed(self, error_message):
        self.status = 'failed'
        self.error_message = error_message
        self.save()

    def mark_as_transcribed(self):
        self.status = 'transcribed'
        self.save()

    def mark_as_analyzed(self):
        self.status = 'analyzed'
        self.is_analyzed = True
        self.save()

