# Generated by Django 5.0.4 on 2024-10-21 05:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('word_learning', '0005_engword_recomend'),
    ]

    operations = [
        migrations.RenameField(
            model_name='engword',
            old_name='recomend',
            new_name='star',
        ),
    ]