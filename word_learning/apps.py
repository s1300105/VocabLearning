
from django.apps import AppConfig


class WordLearningConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'word_learning'

    def ready(self):
        
        import word_learning.signals     