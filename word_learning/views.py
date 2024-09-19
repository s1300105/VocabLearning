from django.shortcuts import render, redirect, get_object_or_404
from .models import EngWord
from .forms import UploadEngWord
from .llm_config import get_llm, example_sentence

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
    llm = get_llm()
    sentence = example_sentence(input_word, llm)
    
    # Debugging output
    print(f"Generated sentence: {sentence}")
    
    return render(request, "word_learning/word_detail.html", {"sentence": sentence})



