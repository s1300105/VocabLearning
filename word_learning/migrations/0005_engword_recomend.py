# Generated by Django 5.0.4 on 2024-10-21 05:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('word_learning', '0004_alter_engword_eng_word'),
    ]

    operations = [
        migrations.AddField(
            model_name='engword',
            name='recomend',
            field=models.BooleanField(default=False),
        ),
    ]
