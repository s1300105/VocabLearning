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
    eng_word = models.CharField(max_length=30)
    meaning = models.CharField(max_length=300, blank=True, null=True)
    part_of_speech = MultiSelectField(max_length=30, 
                                      choices=PART_OF_SPEECH_CHOICES,
                                      max_choices=9,
                                      blank=True, null=True)
    synonyms = models.ManyToManyField('self', blank=True, null=True)
    antonyms = models.ManyToManyField('self', blank=True, null=True)
    cefr = models.CharField(max_length=5, blank=True, null=True)


    def __str__(self):
        return self.eng_word 
    
class ExampleSentence(models.Model):
    sentence = models.CharField(max_length=60)
    eng_word = models.ForeignKey(EngWord, on_delete=models.CASCADE)

class WrittingQuiz(models.Model):
    quiz = models.CharField(max_length=1000)
    llm_quiz = models.BooleanField(default=False) #True means created by llm
    highest_score = models.PositiveIntegerField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

class WrittingAnswer(models.Model):
    quiz = models.ForeignKey(WrittingQuiz, on_delete=models.CASCADE)
    answer = models.CharField(max_length=10000)
    score = models.PositiveIntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], blank=True, null=True)
    scored = models.BooleanField(default=False) # If it has not scored, this is false
    comment = models.CharField(max_length=10000, blank=True, null = True)
    created_at = models.DateTimeField(auto_now_add=True)
