
from django.urls import path
from . import views

app_name = 'english_conversation'

urlpatterns = [
    path('video_chat/', views.video_chat, name='video_chat'),
    path('generate_token/', views.generate_token, name='generate_token'),
    path('ws/lesson/<str:room_name>/', views.LessonConsumer.as_asgi()),
]