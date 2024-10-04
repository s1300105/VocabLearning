from django.db.models.signals import pre_save, post_save
from django.core.exceptions import ValidationError
from .models import WrittingAnswer, WrittingQuiz
from django.dispatch import receiver
from django.db.models import Max

@receiver(pre_save, sender=WrittingAnswer)
def befor_writting_answer(sender, instance, **kwargs):
    print('Signal Called')
    num_instance = WrittingAnswer.objects.filter(scored=False).count()
    if num_instance > 3:
        raise ValidationError("There are already 6 or more unscored WrittingAnswer instances. Cannot save more.")


@receiver(post_save, sender=WrittingAnswer)
def cal_highest_score(sender, instance, **kwargs):
    score = instance.score
    pre_highest = instance.quiz.highest_score
    if pre_highest is None:
        instance.quiz.highest_score = score
        instance.quiz.save()
        print("Highest score updated(first time)")
    elif score > pre_highest:
        instance.quiz.highest_score = score
        instance.quiz.save()
        
        print('Highest score updated')
    