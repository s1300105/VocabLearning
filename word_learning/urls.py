from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("signup", views.signup, name="signup"),
    path("home", views.home, name="home"),
    path("upload_word", views.upload_word, name="upload_word"),
    path("word_detail/<int:pk>", views.word_detail, name="word_detail"),
    path("word_quiz", views.word_quiz, name="word_quiz"),
    path("result", views.result, name='result'),
    path("delete_word/<int:word_id>", views.delete_word, name="delete_word"),
    path("delete_sentence/<int:sentence_id>", views.delete_sentence, name="delete_sentence"),
    path("revise_detail", views.revise_detail, name="revise_detail"),
    path("writting_quiz", views.writting_quiz, name="writting_quiz"),
    path("wr_quiz_page/<int:quiz_id>", views.wr_quiz_page, name="wr_quiz_page"),
    path("writting_fin", views.writting_fin, name="writting_fin"),
    path("score_wr_quiz", views.score_wr_quiz, name="score_wr_quiz"),
    path("error_writting", views.error_writting, name="error_writting"),
    path("makesure_score", views.makesure_score, name="makesure_score"),
    path("answer_history/<int:quiz_id>", views.answer_history, name="answer_history"),
]