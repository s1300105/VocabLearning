from django.db import models

class EngWord(models.Model):
    eng_word = models.CharField(max_length=30, unique=True)
    meaning = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.eng_word 
    


