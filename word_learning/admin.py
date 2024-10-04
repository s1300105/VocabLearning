from django.contrib import admin

from .models import EngWord, ExampleSentence, WrittingQuiz,\
    WrittingAnswer

admin.site.register(EngWord)
admin.site.register(ExampleSentence)
admin.site.register(WrittingQuiz)
admin.site.register(WrittingAnswer)