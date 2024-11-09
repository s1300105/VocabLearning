from django.urls import path
from . import views

app_name = 'video_chat'

urlpatterns = [
    path('video_lesson/', views.video_lesson, name='video_lesson'),
    path('make_token/', views.make_token, name='make_token'),
    path('recording-complete/', views.handle_recording_complete, name='recording_complete'),
    path('player/', views.player_view, name='player'),
    path('go_transcribe/', views.go_transcribe, name="go_transcribe"),
    path('transcribe_audio/', views.transcribe_audio, name="transcribe_audio"),  # 追加
]




"""
urlpatterns = [
    path('video_lesson/', views.video_lesson, name='video_lesson'),
    path('make_token/', views.make_token, name='make_token'),
    path('recording-complete/', views.handle_recording_complete, name='recording_complete'),
    path('player/', views.audio_player_view, name='audio_player_list'),  # 全ての録音を表示
    path('player/<str:composition_sid>/', 
         views.audio_player_view, 
         name='audio_player'),
    path('compositions/<str:composition_sid>/url/', 
         views.get_composition_url, 
         name='get_composition_url'),
    path('api/compositions/<str:composition_sid>/status/',
         views.check_composition_status,
         name='check_composition_status'),
]
"""