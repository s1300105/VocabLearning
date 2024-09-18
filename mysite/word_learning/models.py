from django.db import models

class EngWord(models.Model):
    eng_word = models.CharField(max_length=30, unique=True)
    meaning = models.ManyToManyField("JapaWord")

    def __str__(self):
        return self.eng_word
    
class JapaWord(models.Model):
    japa_word = models.CharField(max_length=30, unique=True)
    

    def __str__(self):
        return self.japa_word

