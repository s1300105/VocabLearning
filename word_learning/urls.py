from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("upload_word", views.upload_word, name="upload_word"),
    path("word_detail/<str:pk>", views.word_detail, name="word_detail"),
]