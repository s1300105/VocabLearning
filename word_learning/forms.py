from django.forms import ModelForm
from django import forms
from .models import EngWord, WrittingAnswer, CustomUser
from django.contrib.auth.forms import UserCreationForm


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

class SignUpForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "password1",
            "password2"

        )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # オプション: フィールドにCSSクラスを追加
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


