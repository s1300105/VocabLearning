import logging

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import MAX_UNSCORED_ANSWERS, WrittingAnswer

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=WrittingAnswer)
def before_writting_answer(sender, instance, **kwargs):
    """未採点の回答が上限に達しているユーザーの新規回答を拒否する。

    採点結果の保存（既存レコードの更新）は常に許可する。
    """
    if not instance._state.adding:
        return
    num_unscored = WrittingAnswer.objects.filter(user_id=instance.user_id, scored=False).count()
    if num_unscored >= MAX_UNSCORED_ANSWERS:
        raise ValidationError(
            f"You already have {MAX_UNSCORED_ANSWERS} or more unscored answers. "
            "Please score your answers first."
        )


@receiver(post_save, sender=WrittingAnswer)
def cal_highest_score(sender, instance, **kwargs):
    """採点済みの回答が保存されたら、問題の最高点を更新する"""
    score = instance.score
    if score is None:
        return
    quiz = instance.quiz
    if quiz.highest_score is None or score > quiz.highest_score:
        quiz.highest_score = score
        quiz.save(update_fields=['highest_score'])
        logger.debug("Highest score of quiz %s updated to %s", quiz.pk, score)
