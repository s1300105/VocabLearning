# Generated by Django 5.0.4 on 2024-11-17 11:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('word_learning', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='engword',
            name='antonyms',
            field=models.ManyToManyField(blank=True, to='word_learning.engword'),
        ),
        migrations.AlterField(
            model_name='engword',
            name='synonyms',
            field=models.ManyToManyField(blank=True, to='word_learning.engword'),
        ),
    ]
