from django.forms import ModelForm
from django import forms
from .models import EngWord, WrittingAnswer

class UploadEngWord(ModelForm):
    class Meta:
        model = EngWord
        fields = ['eng_word', 'meaning']


class ReviseDetail(ModelForm):
    class Meta:
        model = EngWord
        fields = ['part_of_speech', 'synonyms', 'antonyms']

class WrittingForm(ModelForm):
    class Meta:
        model = WrittingAnswer
        fields = ['answer']
        widgets = {
            'answer': forms.Textarea(attrs={
                'cols':80,
                'rows':20,
                'placeholder': 'Your answer here...'
            }),
        }


