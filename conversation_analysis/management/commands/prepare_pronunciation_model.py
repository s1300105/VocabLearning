"""発音チェックに使う音素認識モデルと発音辞書を事前にダウンロードする（初回のみ、約1.3GB）。

    python manage.py prepare_pronunciation_model

実行しなくても初回の発音チェック時に自動でダウンロードされるが、その分待ち時間が長くなる。
"""
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Download the phoneme recognition model and pronunciation dictionary.'

    def handle(self, *args, **options):
        from conversation_analysis.pronunciation import acoustic
        from conversation_analysis.pronunciation.phonemes import lookup

        self.stdout.write(f'Loading {settings.PRONUNCIATION_MODEL} ...')
        model = acoustic.load_model()
        lookup('hello')
        self.stdout.write(self.style.SUCCESS(
            f'Ready: {len(model.vocab)} phoneme symbols, pronunciation dictionary loaded.'))
