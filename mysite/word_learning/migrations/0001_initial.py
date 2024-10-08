# Generated by Django 5.0.4 on 2024-09-17 14:41

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Eng_Word',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('eng_word', models.CharField(max_length=30)),
            ],
        ),
        migrations.CreateModel(
            name='Choice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('japa_word', models.CharField(max_length=30)),
                ('eng_mean', models.ManyToManyField(to='word_learning.eng_word')),
            ],
        ),
    ]
