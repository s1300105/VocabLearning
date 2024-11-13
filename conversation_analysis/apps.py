# conversation_analysis/apps.py
from django.apps import AppConfig

class ConversationAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'conversation_analysis'
    verbose_name = 'Conversation Analysis'

    def ready(self):
        # SpaCyモデルの事前ロード
        import spacy
        try:
            spacy.load('en_core_web_sm')
        except OSError:
            from spacy.cli import download
            download('en_core_web_sm')