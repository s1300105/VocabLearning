import logging
import re
from random import choice, sample

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as BaseLoginView
from django.contrib.auth.views import LogoutView as BaseLogoutView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from .forms import LoginForm, ReviseDetail, SignUpForm, WrittingForm
from .llm_config import (example_sentence, get_llm, get_llm_writting,
                         getllm_eval_wr, llm_eval_wr, writingquiz_llm)
from .models import (MAX_UNSCORED_ANSWERS, EngWord, ExampleSentence, Favorite,
                     WrittingAnswer, WrittingQuiz)

logger = logging.getLogger(__name__)

QUIZ_CHOICES = 4  # 単語クイズの選択肢の数


def index(request):
    return render(request, "word_learning/index.html")


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            user = authenticate(
                request,
                username=form.cleaned_data.get('email'),
                password=form.cleaned_data.get('password1'),
            )
            if user is not None:
                login(request, user)
                return redirect("index")
            logger.warning("Authentication failed right after signup")
    else:
        form = SignUpForm()
    return render(request, "word_learning/signup.html", {"form": form})


class LoginView(BaseLoginView):
    form_class = LoginForm
    template_name = "word_learning/login.html"


class LogoutView(BaseLogoutView):
    success_url = reverse_lazy("index")


@login_required
def favorite_words(request):
    words = EngWord.objects.filter(favorite__user=request.user)
    return render(request, "word_learning/favorite_word.html", {'words': words})


@login_required
@require_POST
def remove_favorite(request, word_id):
    """お気に入りから外す（単語そのものは辞書に残す）"""
    Favorite.objects.filter(user=request.user, word_id=word_id).delete()
    return redirect("favorite_words")


@login_required
def word_detail(request, pk):
    word_obj = get_object_or_404(EngWord, id=pk)

    if request.method == "POST" and "generate_sentence" in request.POST:
        llm = get_llm()
        sentence = example_sentence(word_obj.eng_word, llm)
        max_length = ExampleSentence._meta.get_field('sentence').max_length
        ExampleSentence.objects.create(
            user=request.user,
            eng_word=word_obj,
            sentence=sentence[:max_length],
        )
        # 再読み込みで二重生成しないようにリダイレクトする
        return redirect("word_detail", pk=pk)

    context = {
        'input_word': word_obj.eng_word,
        'all_sentences': ExampleSentence.objects.filter(eng_word=word_obj, user=request.user),
        'word_id': pk,
        'part_of_speech': word_obj.part_of_speech,
        'synonyms': [w.eng_word for w in word_obj.synonyms.all()],
        'antonyms': [w.eng_word for w in word_obj.antonyms.all()],
        'meaning': word_obj.meaning,
        'cefr': word_obj.cefr,
    }
    return render(request, "word_learning/word_detail.html", context)


@login_required
def word_quiz(request):
    if not request.user.cefr:
        messages.error(request, "Please set your CEFR level before taking the word quiz.")
        return redirect("index")

    word_ids = list(EngWord.objects.filter(cefr=request.user.cefr).values_list('id', flat=True))
    if len(word_ids) < QUIZ_CHOICES:
        messages.error(request, f"Not enough words registered for level {request.user.cefr}.")
        return redirect("index")

    answer_id = choice(word_ids)
    answer_word = EngWord.objects.get(id=answer_id)
    request.session['answer_id'] = answer_id
    request.session['answer'] = answer_word.eng_word
    request.session['answer_meaning'] = answer_word.meaning

    other_ids = sample([i for i in word_ids if i != answer_id], QUIZ_CHOICES - 1)
    other_words = list(EngWord.objects.filter(id__in=other_ids).values_list('eng_word', flat=True))
    all_words = [answer_word.eng_word] + other_words
    shuffled_words = sample(all_words, len(all_words))

    return render(request, "word_learning/word_quiz.html", {
        "answer_japa": answer_word.meaning,
        "shuffled_words": shuffled_words,
    })


@login_required
def result(request):
    answer = request.session.get('answer')
    if request.method != "POST" or answer is None:
        return redirect("word_quiz")

    meaning = request.session.get('answer_meaning') or ''
    answer_id = request.session.get('answer_id')
    selected_word = request.POST.get('word_choice')
    if selected_word == answer:
        result_text = f"Your answer is correct!!! ({answer} => {meaning})"
    else:
        result_text = f"No, Your answer is incorrect ({answer} => {meaning})"
    return render(request, "word_learning/result.html", {
        "result": result_text,
        "answer": answer,
        "answer_id": answer_id,
    })


@login_required
@require_POST
def delete_sentence(request, sentence_id):
    sentence = get_object_or_404(ExampleSentence, id=sentence_id, user=request.user)
    word_id = sentence.eng_word_id
    sentence.delete()
    return redirect("word_detail", pk=word_id)


@login_required
def revise_detail(request, pk):
    word = get_object_or_404(EngWord, id=pk)
    if request.method == "POST":
        form_detail = ReviseDetail(request.POST, instance=word)
        if form_detail.is_valid():
            form_detail.save()
            return redirect("word_detail", pk=pk)
    else:
        form_detail = ReviseDetail(instance=word)

    return render(request, "word_learning/revise_detail.html", {"form_detail": form_detail, "word": word})


@login_required
def writting_quiz(request):
    if request.method == "POST" and "writting_quiz" in request.POST:
        llm = get_llm_writting()
        quiz = writingquiz_llm(llm)
        WrittingQuiz.objects.create(user=request.user, quiz=quiz, llm_quiz=True)
        return redirect("writting_quiz")

    all_quiz = WrittingQuiz.objects.filter(user=request.user).order_by('-created_at')
    paginator = Paginator(all_quiz, 10)
    quiz_page = paginator.get_page(request.GET.get('page', 1))

    return render(request, "word_learning/writting_quiz.html", {"all_quiz": all_quiz, "quiz_page": quiz_page})


def _unscored_answers(user):
    return WrittingAnswer.objects.filter(user=user, scored=False)


@login_required
def wr_quiz_page(request, quiz_id):
    if _unscored_answers(request.user).count() >= MAX_UNSCORED_ANSWERS:
        messages.error(
            request,
            f"You already have {MAX_UNSCORED_ANSWERS} or more unscored answers. Please score your answers first.",
        )
        return redirect('error_writting')

    quiz = get_object_or_404(WrittingQuiz, id=quiz_id, user=request.user)

    if request.method == 'POST':
        form = WrittingForm(request.POST)
        if form.is_valid():
            answer = form.save(commit=False)
            answer.user = request.user
            answer.quiz = quiz
            try:
                answer.save()
            except ValidationError as e:
                messages.error(request, e.messages[0])
                return redirect('error_writting')
            return redirect('writting_fin')
    else:
        form = WrittingForm()

    return render(request, "word_learning/wr_quiz_page.html", {"quiz": quiz, "form": form})


@login_required
def writting_fin(request):
    prog_answers = _unscored_answers(request.user).select_related('quiz').order_by("created_at")
    return render(request, "word_learning/writting_fin.html", {'prog_answers': prog_answers})


@login_required
def score_wr_quiz(request):
    """未採点の回答を LLM で採点する"""
    prog_answers = list(_unscored_answers(request.user).select_related('quiz').order_by("created_at"))

    results = []
    if prog_answers:
        llm = getllm_eval_wr()
        for answer_obj in prog_answers:
            content = f"<Question>: {answer_obj.quiz.quiz} <Answer>: {answer_obj.answer}"
            text = llm_eval_wr(llm, content)

            score_match = re.search(r'score:\s*(\d+)', text, re.IGNORECASE)
            if score_match:
                answer_obj.score = min(int(score_match.group(1)), 100)
                answer_obj.scored = True
                answer_obj.comment = text
                answer_obj.save()

            results.append((answer_obj.quiz.quiz, answer_obj.answer, text))

    return render(request, "word_learning/score_wr_quiz.html", {"quiz_ans_comment": results})


@login_required
def error_writting(request):
    return render(request, "word_learning/error_writting.html")


@login_required
def makesure_score(request):
    return render(request, "word_learning/makesure_score.html")


@login_required
def answer_history(request, quiz_id):
    quiz = get_object_or_404(WrittingQuiz, id=quiz_id, user=request.user)
    answers = WrittingAnswer.objects.filter(quiz=quiz, user=request.user).order_by('-created_at')
    return render(request, "word_learning/answer_history.html", {'answers': answers})
