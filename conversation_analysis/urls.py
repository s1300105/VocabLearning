from django.urls import path
from . import views

app_name = 'conversation_analysis'

urlpatterns = [
    path('word_freq/', views.word_freq, name='word_freq'),

]