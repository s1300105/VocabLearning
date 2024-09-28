from django.db import models
from multiselectfield import MultiSelectField
from django.core.validators import MaxValueValidator, MinValueValidator

class EngWord(models.Model):
    PART_OF_SPEECH_CHOICES = [
        ('noun', 'Noun'),
        ('verb', 'Verb'),
        ('adjective', 'Adjective'),
        ('adverb', 'Adverb'),
        ('pronoun', 'Pronoun'),
        ('preposition', 'Preposition'),
        ('conjunction', 'Conjunction'),
        ('interjection', 'Interjection'),
        ('article', 'Article'),
    ]
    eng_word = models.CharField(max_length=30, unique=True)
    meaning = models.CharField(max_length=30, blank=True)
    part_of_speech = MultiSelectField(max_length=30, 
                                      choices=PART_OF_SPEECH_CHOICES,
                                      max_choices=9,
                                      blank=True)
    synonyms = models.ManyToManyField('self', blank=True)
    antonyms = models.ManyToManyField('self', blank=True)


    def __str__(self):
        return self.eng_word 
    
class ExampleSentence(models.Model):
    sentence = models.CharField(max_length=60)
    eng_word = models.ForeignKey(EngWord, on_delete=models.CASCADE)

class WrittingQuiz(models.Model):
    quiz = models.CharField(max_length=1000)
    llm_quiz = models.BooleanField(default=False) #True means created by llm
    score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    created_at = models.DateTimeField(auto_now_add=True)


