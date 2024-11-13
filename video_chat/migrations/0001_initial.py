# Generated by Django 5.0.4 on 2024-11-13 01:50

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Recording',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_sid', models.CharField(max_length=255)),
                ('audio_url', models.URLField(max_length=500)),
                ('duration', models.IntegerField()),
                ('transcript', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('transcribed', 'Transcribed'), ('analyzed', 'Analyzed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('is_analyzed', models.BooleanField(default=False)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['room_sid'], name='video_chat__room_si_367393_idx'), models.Index(fields=['user', '-created_at'], name='video_chat__user_id_b45868_idx'), models.Index(fields=['status'], name='video_chat__status_179ebf_idx')],
            },
        ),
    ]
