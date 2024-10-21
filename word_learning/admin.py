from django.contrib import admin
from django.contrib.auth import get_user_model


from .models import EngWord, ExampleSentence, WrittingQuiz,\
    WrittingAnswer

CustomUser = get_user_model()

admin.site.register(EngWord)
admin.site.register(ExampleSentence)
admin.site.register(WrittingQuiz)
admin.site.register(WrittingAnswer)
admin.site.register(CustomUser)