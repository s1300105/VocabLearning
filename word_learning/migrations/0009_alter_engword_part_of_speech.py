# Generated by Django 5.0.4 on 2024-09-20 07:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('word_learning', '0008_engword_antonyms_engword_part_of_speech_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='engword',
            name='part_of_speech',
            field=models.CharField(blank=True, choices=[('noun', 'Noun'), ('verb', 'Verb'), ('adjective', 'Adjective'), ('adverb', 'Adverb'), ('pronoun', 'Pronoun'), ('preposition', 'Preposition'), ('conjunction', 'Conjunction'), ('interjection', 'Interjection'), ('article', 'Article')], max_length=30),
        ),
    ]
