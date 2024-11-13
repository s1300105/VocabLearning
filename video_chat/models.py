from django.db import models
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User

class Recording(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('transcribed', 'Transcribed'),
        ('analyzed', 'Analyzed'),
        ('failed', 'Failed')
    ]
    
    room_sid = models.CharField(max_length=255)
    audio_url = models.URLField(max_length=500)
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

