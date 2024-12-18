# Generated by Django 5.0.4 on 2024-11-13 01:50

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('video_chat', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConversationAnalysis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('word_count', models.IntegerField(default=0)),
                ('is_completed', models.BooleanField(default=False)),
                ('word_frequency', models.JSONField(default=dict)),
                ('pos_analysis', models.JSONField(default=dict)),
                ('grammar_score', models.FloatField(null=True)),
                ('recording', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='video_chat.recording')),
            ],
        ),
        migrations.CreateModel(
            name='POSDistribution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pos_tag', models.CharField(max_length=20)),
                ('count', models.IntegerField()),
                ('percentage', models.FloatField()),
                ('analysis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='conversation_analysis.conversationanalysis')),
            ],
            options={
                'ordering': ['-count'],
            },
        ),
        migrations.CreateModel(
            name='WordFrequency',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('word', models.CharField(max_length=100)),
                ('count', models.IntegerField()),
                ('pos_tag', models.CharField(max_length=20)),
                ('lemma', models.CharField(max_length=100)),
                ('analysis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='conversation_analysis.conversationanalysis')),
            ],
            options={
                'verbose_name_plural': 'Word frequencies',
                'ordering': ['-count'],
            },
        ),
    ]
