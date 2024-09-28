from django.forms import ModelForm
from .models import EngWord

class UploadEngWord(ModelForm):
    class Meta:
        model = EngWord
        fields = ['eng_word', 'meaning']


class ReviseDetail(ModelForm):
    class Meta:
        model = EngWord
        fields = ['part_of_speech', 'synonyms', 'antonyms']


