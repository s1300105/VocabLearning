# conversation_analysis/urls.py
from django.urls import path
from . import views

app_name = 'conversation_analysis'

urlpatterns = [
     path('recording/<int:recording_id>/analysis/', 
         views.analysis_detail, 
         name='analysis_detail'),
     
     
     path('audio-analysis/', views.audio_analysis, name='audio_analysis'),  # パス名を変更
     path('audio-analysis/generate-audio/', views.generate_audio, name='generate_audio'),
     path('audio-analysis/get-audio/<str:filename>', views.get_audio_file, name='get_audio_file'),

    #path('analyses/', 
         #views.analysis_list, 
         #name='analysis_list'),
         
    #path('api/analysis/<int:analysis_id>/data/', 
         #views.get_analysis_data, 
         #name='get_analysis_data'),
         
    #path('recording/<int:recording_id>/reanalyze/', 
         #views.reanalyze_recording, 
         #name='reanalyze_recording'),
]