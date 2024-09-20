from django.shortcuts import render, redirect, get_object_or_404
from .models import EngWord, ExampleSentence
from .forms import UploadEngWord
from .llm_config import get_llm, example_sentence
from random import sample, choice

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
    input_word = get_object_or_404(EngWord, id=pk).eng_word

    if request.method == "POST" and "generate_sentence" in request.POST:
        llm = get_llm()
        sentence = example_sentence(input_word, llm)
        instance = ExampleSentence(
            sentence=sentence,
            eng_word=get_object_or_404(EngWord, id=pk)
        )
        instance.save()

    all_sentences = []
    all_sentences_obj = ExampleSentence.objects.filter(eng_word__eng_word=input_word)
    for obj in all_sentences_obj:
        all_sentences.append(obj.sentence)
    
    context = {
        'input_word':input_word,
        'all_sentences':all_sentences,
        'word_id':pk
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

