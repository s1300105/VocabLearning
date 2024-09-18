from django.shortcuts import render
from .models import EngWord, JapaWord

def home(request):
    words = EngWord.objects.all().order_by('eng_word')
    return render(request, "word_learning/home.html", {"words":words})

