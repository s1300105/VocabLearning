from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (MAX_UNSCORED_ANSWERS, EngWord, ExampleSentence, Favorite,
                     WrittingAnswer, WrittingQuiz)

User = get_user_model()


class WordLearningTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='me@example.com', password='pass-12345', username='me', cefr='A1')
        self.other = User.objects.create_user(email='other@example.com', password='pass-12345', username='other')
        self.client.force_login(self.user)


class LoginRequiredTests(TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        for name, kwargs in [
            ('favorite_words', {}),
            ('word_quiz', {}),
            ('writting_quiz', {}),
            ('score_wr_quiz', {}),
            ('wr_quiz_page', {'quiz_id': 1}),
            ('answer_history', {'quiz_id': 1}),
        ]:
            response = self.client.get(reverse(name, kwargs=kwargs))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse('login'), response['Location'], name)


class WritingAnswerTests(WordLearningTestBase):
    def setUp(self):
        super().setUp()
        self.quiz = WrittingQuiz.objects.create(user=self.user, quiz='Describe your hometown.')

    def test_submitting_answer_saves_it_for_current_user(self):
        response = self.client.post(reverse('wr_quiz_page', args=[self.quiz.id]), {'answer': 'My hometown is small.'})

        self.assertRedirects(response, reverse('writting_fin'))
        answer = WrittingAnswer.objects.get()
        self.assertEqual(answer.user, self.user)
        self.assertEqual(answer.quiz, self.quiz)

    def test_cannot_open_other_users_quiz(self):
        other_quiz = WrittingQuiz.objects.create(user=self.other, quiz='Secret')
        response = self.client.get(reverse('wr_quiz_page', args=[other_quiz.id]))
        self.assertEqual(response.status_code, 404)

    def test_unscored_limit_blocks_new_answers(self):
        for i in range(MAX_UNSCORED_ANSWERS):
            WrittingAnswer.objects.create(user=self.user, quiz=self.quiz, answer=f'a{i}')

        response = self.client.get(reverse('wr_quiz_page', args=[self.quiz.id]))
        self.assertRedirects(response, reverse('error_writting'))

    def test_unscored_limit_is_per_user(self):
        for i in range(MAX_UNSCORED_ANSWERS):
            WrittingAnswer.objects.create(user=self.other, quiz=self.quiz, answer=f'a{i}')

        response = self.client.get(reverse('wr_quiz_page', args=[self.quiz.id]))
        self.assertEqual(response.status_code, 200)

    def test_scoring_works_even_when_unscored_limit_is_reached(self):
        answers = [
            WrittingAnswer.objects.create(user=self.user, quiz=self.quiz, answer=f'a{i}')
            for i in range(MAX_UNSCORED_ANSWERS)
        ]

        with mock.patch('word_learning.views.getllm_eval_wr'), \
                mock.patch('word_learning.views.llm_eval_wr', return_value='Good job. score: 80'):
            response = self.client.get(reverse('score_wr_quiz'))

        self.assertEqual(response.status_code, 200)
        for answer in answers:
            answer.refresh_from_db()
            self.assertTrue(answer.scored)
            self.assertEqual(answer.score, 80)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.highest_score, 80)

    def test_new_answer_to_quiz_with_highest_score_does_not_crash(self):
        self.quiz.highest_score = 70
        self.quiz.save()

        WrittingAnswer.objects.create(user=self.user, quiz=self.quiz, answer='new answer')

        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.highest_score, 70)

    def test_answer_history_shows_only_own_answers(self):
        WrittingAnswer.objects.create(user=self.user, quiz=self.quiz, answer='mine')
        other_quiz = WrittingQuiz.objects.create(user=self.other, quiz='Q')
        WrittingAnswer.objects.create(user=self.other, quiz=other_quiz, answer='theirs')

        self.assertContains(self.client.get(reverse('answer_history', args=[self.quiz.id])), 'mine')
        self.assertEqual(self.client.get(reverse('answer_history', args=[other_quiz.id])).status_code, 404)


class WordTests(WordLearningTestBase):
    def setUp(self):
        super().setUp()
        self.word = EngWord.objects.create(eng_word='apple', meaning='りんご', cefr='A1')

    def test_revise_detail_updates_existing_word(self):
        synonym = EngWord.objects.create(eng_word='fruit', cefr='A1')

        response = self.client.post(reverse('revise_detail', args=[self.word.id]), {
            'part_of_speech': ['noun'],
            'synonyms': [synonym.id],
        })

        self.assertRedirects(response, reverse('word_detail', args=[self.word.id]))
        self.assertEqual(EngWord.objects.count(), 2)  # 新しい単語は作られない
        self.word.refresh_from_db()
        self.assertEqual(list(self.word.part_of_speech), ['noun'])
        self.assertEqual(list(self.word.synonyms.all()), [synonym])

    def test_remove_favorite_keeps_word(self):
        Favorite.objects.create(user=self.user, word=self.word)

        response = self.client.post(reverse('remove_favorite', args=[self.word.id]))

        self.assertRedirects(response, reverse('favorite_words'))
        self.assertFalse(Favorite.objects.exists())
        self.assertTrue(EngWord.objects.filter(id=self.word.id).exists())

    def test_generate_sentence_saves_with_user(self):
        with mock.patch('word_learning.views.get_llm'), \
                mock.patch('word_learning.views.example_sentence', return_value='I ate an apple.'):
            response = self.client.post(reverse('word_detail', args=[self.word.id]), {'generate_sentence': ''})

        self.assertRedirects(response, reverse('word_detail', args=[self.word.id]))
        sentence = ExampleSentence.objects.get()
        self.assertEqual(sentence.user, self.user)
        self.assertEqual(sentence.sentence, 'I ate an apple.')

    def test_cannot_delete_other_users_sentence(self):
        sentence = ExampleSentence.objects.create(user=self.other, eng_word=self.word, sentence='x')

        response = self.client.post(reverse('delete_sentence', args=[sentence.id]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(ExampleSentence.objects.filter(id=sentence.id).exists())

    def test_word_quiz_without_cefr_redirects(self):
        self.user.cefr = None
        self.user.save()
        self.assertRedirects(self.client.get(reverse('word_quiz')), reverse('index'))

    def test_word_quiz_with_too_few_words_redirects(self):
        self.assertRedirects(self.client.get(reverse('word_quiz')), reverse('index'))

    def test_word_quiz_and_result(self):
        for w in ['banana', 'cherry', 'grape']:
            EngWord.objects.create(eng_word=w, meaning=w, cefr='A1')

        response = self.client.get(reverse('word_quiz'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['shuffled_words']), 4)

        answer = self.client.session['answer']
        response = self.client.post(reverse('result'), {'word_choice': answer})
        self.assertContains(response, 'correct!!!')
