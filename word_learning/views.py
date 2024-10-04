from django.shortcuts import render, redirect, get_object_or_404
from .models import EngWord, ExampleSentence, WrittingQuiz, WrittingAnswer
from .forms import UploadEngWord, ReviseDetail, WrittingForm
from .llm_config import get_llm, example_sentence, writingquiz_llm, get_llm_writting, getllm_eval_wr, llm_eval_wr
from random import sample, choice
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.contrib import messages
import re

def home(request):
    words = EngWord.objects.all().order_by('eng_word')
    return render(request, "word_learning/home.html", {"words":words})

def upload_word(request):
    if request.method == "POST":
        form_eng = UploadEngWord(request.POST)
        
        if form_eng.is_valid():
            form_eng.save() 
            return redirect("home")
    else:
        form_eng = UploadEngWord()
        
    
    return render(request, "word_learning/upload_eng.html", {"form_eng":form_eng})



def word_detail(request, pk):

    request.session['word_id'] = pk
    word_obj = get_object_or_404(EngWord, id=pk)
    input_word = word_obj.eng_word
    part_of_speech = word_obj.part_of_speech
    synonym_objs = word_obj.synonyms.all()
    synonym = [synonym.eng_word for synonym in synonym_objs ]
    antonym_objs = word_obj.antonyms.all()
    antonym = [antonym.eng_word for antonym in antonym_objs]

    

    if request.method == "POST" and "generate_sentence" in request.POST:
        llm = get_llm()
        sentence = example_sentence(input_word, llm)
        instance = ExampleSentence(
            sentence=sentence,
            eng_word=get_object_or_404(EngWord, id=pk)
        )
        instance.save()
  
    all_sentences = ExampleSentence.objects.filter(eng_word__eng_word=input_word)
    context = {
        'input_word':input_word,
        'all_sentences':all_sentences,
        'word_id':pk,
        'part_of_speech':part_of_speech,
        'synonyms':synonym,
        'antonyms':antonym
    }


    
    return render(request, "word_learning/word_detail.html", context)

def word_quiz(request):
    word_ids = list(EngWord.objects.values_list('id', flat=True))

    answer_id = choice(word_ids)
    answer_word = EngWord.objects.get(id=answer_id)
    answer_japa = answer_word.meaning
    request.session['answer_id'] = answer_id
    request.session['answer'] = answer_word.eng_word
    request.session['answer_meaning'] = answer_word.meaning

    remaining_ids = [id for id in word_ids if id != answer_id]
    other_ids = sample(remaining_ids, 3)
    other_words = []
    for other_id in other_ids:
        other_word = EngWord.objects.get(id=other_id).eng_word
        other_words.append(other_word)

    all_words = [answer_word] + other_words
    shuffled_words = sample(all_words, len(all_words))

    return render(request, "word_learning/word_quiz.html", {"answer_japa":answer_japa, "shuffled_words":shuffled_words})



def result(request):
    if request.method == "POST":
        
        selected_word = request.POST.get('word_choice')
        answer = request.session['answer']
        meaning = request.session['answer_meaning']
        answer_id = request.session['answer_id']
        if selected_word == answer:   
            result = "Your answer is correct!!! (" + answer + " => " + meaning + ")"
        else:
            result = "No, Your answer is incorrect (" + answer + " => " + meaning + ")"
        return render(request, "word_learning/result.html", {"result":result, "answer":answer, "answer_id":answer_id})

def delete_word(request, word_id):
    if request.method == "POST" and "delete_word" in request.POST:
        word = EngWord.objects.get(id=word_id)
        word.delete()
        return redirect("home")


def delete_sentence(request, sentence_id):
    word_id = request.session['word_id']
    if request.method == "POST" and "delete" in request.POST:
        sentence = ExampleSentence.objects.get(id=sentence_id)
        sentence.delete()
        return redirect("word_detail", pk=word_id)




def revise_detail(request):
    word_id = request.session['word_id']
    if request.method == "POST":
        form_detail = ReviseDetail(request.POST)
        if form_detail.is_valid():
            form_detail.save()
            return redirect("word_detail", pk=word_id)
    else:
        form_detail = ReviseDetail()

    return render(request, "word_learning/revise_detail.html", {"form_detail":form_detail})


def writting_quiz(request):

    if request.method == "POST" and "writting_quiz" in request.POST:
        llm = get_llm_writting()
        quiz = writingquiz_llm(llm)
        instance = WrittingQuiz(
            quiz = quiz,
            llm_quiz = True
        )
        instance.save()
    
    all_quiz = WrittingQuiz.objects.all().order_by('-created_at')
    paginator = Paginator(all_quiz, 10)
    page_number = request.GET.get('page', 1)
    quiz_page = paginator.get_page(page_number)

    context = {"all_quiz":all_quiz,
               
               "quiz_page":quiz_page}

    return render(request, "word_learning/writting_quiz.html", context)


def wr_quiz_page(request, quiz_id):
    prog_answer = WrittingAnswer.objects.filter(scored=False).count()
    if prog_answer > 3:
        messages.error(request, "There are already 6 or more unscored WrittingAnswer instances. Please score your answers first.")
        return redirect('error_writting')
    quiz = WrittingQuiz.objects.get(id=quiz_id)
    
    if request.method == 'POST':
        form = WrittingForm(request.POST)
        if form.is_valid():
            try:
                answer = form.save(commit=False)
                answer.quiz = quiz
                answer.save()
                return redirect('writting_fin')
            except ValidationError as e:
                messages.error(request, "The number of non scored files are more than limit. Please score your writting quizzes answer")
                return redirect('error_page')
        
    else:
        form = WrittingForm()
    
    context = {"quiz":quiz, "form":form}
    

    return render(request, "word_learning/wr_quiz_page.html", context)

def writting_fin(request):
    prog_answers = WrittingAnswer.objects.filter(scored=False).order_by("created_at")
    context = {'prog_answers':prog_answers}
    
    return render(request, "word_learning/writting_fin.html", context)

def score_wr_quiz(request):
    # スコアがまだついていない回答を取得
    prog_answers = WrittingAnswer.objects.filter(scored=False).order_by("created_at")
    
    llm = getllm_eval_wr()  # LLM モデルを取得
    
    output = []
    quiz = []
    answer = []
    
    for answer_obj in prog_answers:
        answer_text = answer_obj.answer  # `answer` 文字列を取得
        quiz_text = answer_obj.quiz.quiz  # `quiz` の質問文を取得

        answer.append(answer_text)
        quiz.append(quiz_text)
        
        # 評価するためのコンテンツを作成
        content = f"<Question>: {quiz_text} <Answer>: {answer_text}"
        text = llm_eval_wr(llm, content)  # LLMで回答を評価
        
        # 正規表現でスコアを抽出
        score_match = re.search(r'score:\s*(\d+)', text)
        
        if score_match:
            score = int(score_match.group(1))  # スコアを整数に変換して取得
            answer_obj.score = score  # WrittingAnswer の score フィールドにスコアを設定
            answer_obj.scored = True  # スコアがついたことを記録
            answer_obj.comment = text
            answer_obj.save()  # 変更をデータベースに保存
        
            
        
        output.append(text)  # LLM の出力をリストに追加
    quiz_ans_comment = zip(quiz, answer, output)
    context = {
        "quiz_ans_comment":quiz_ans_comment
    }
    
    return render(request, "word_learning/score_wr_quiz.html", context)



    

def error_writting(request):
    return render(request, "word_learning/error_writting.html")

def makesure_score(request):
    return render(request, "word_learning/makesure_score.html")

def answer_history(request, quiz_id):
    answers = WrittingAnswer.objects.filter(quiz = quiz_id)
    context = {
        'answers':answers
    }
    return render(request, "word_learning/answer_history.html", context)