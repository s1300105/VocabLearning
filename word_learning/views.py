from django.shortcuts import render, redirect, get_object_or_404
from .models import EngWord, ExampleSentence, WrittingQuiz
from .forms import UploadEngWord, ReviseDetail
from .llm_config import get_llm, example_sentence, writingquiz_llm, get_llm_writting
from random import sample, choice
from django.core.paginator import Paginator

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
    
    all_quiz = WrittingQuiz.objects.all().order_by('score', '-created_at')
    paginator = Paginator(all_quiz, 10)
    page_number = request.GET.get('page', 1)
    quiz_page = paginator.get_page(page_number)

    context = {"all_quiz":all_quiz,
               "quiz_page":quiz_page}

    return render(request, "word_learning/writting_quiz.html", context)


def wr_quiz_page(request, pk):
    quiz = WrittingQuiz.objects.get(id=pk)
    context = {"quiz":quiz}
    return render(request, "word_learning/wr_quiz_page.html", context)