# Generated by Django 5.0.4 on 2024-11-17 11:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversation_analysis', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversationanalysis',
            name='mltd_score',
            field=models.FloatField(null=True),
        ),
    ]
