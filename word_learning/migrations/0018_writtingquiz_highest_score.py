# Generated by Django 5.0.4 on 2024-10-04 01:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('word_learning', '0017_alter_writtinganswer_score'),
    ]

    operations = [
        migrations.AddField(
            model_name='writtingquiz',
            name='highest_score',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
