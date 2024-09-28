from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("upload_word", views.upload_word, name="upload_word"),
    path("word_detail/<int:pk>", views.word_detail, name="word_detail"),
    path("word_quiz", views.word_quiz, name="word_quiz"),
    path("result", views.result, name='result'),
    path("delete_word/<int:word_id>", views.delete_word, name="delete_word"),
    path("delete_sentence/<int:sentence_id>", views.delete_sentence, name="delete_sentence"),
    path("revise_detail", views.revise_detail, name="revise_detail"),
    path("writting_quiz", views.writting_quiz, name="writting_quiz"),
    path("wr_quiz_page/<int:pk>", views.wr_quiz_page, name="wr_quiz_page"),
]