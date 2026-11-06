import importlib.util
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from video_chat.models import Recording

from .views import AUDIO_FILES_SESSION_KEY
from .vocab_diversity_analysis import VocabularyDiversityAnalyzer

User = get_user_model()
HAS_LIBROSA = importlib.util.find_spec('librosa') is not None


class AudioEndpointsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='me@example.com', password='pass-12345', username='me')
        self.other = User.objects.create_user(email='other@example.com', password='pass-12345', username='other')
        self.client.force_login(self.user)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_anonymous_users_cannot_use_pronunciation_apis(self):
        self.client.logout()
        for name in ['generate_audio', 'analyze_pronunciation']:
            response = self.client.post(reverse(f'conversation_analysis:{name}'), {'room_sid': 'RM1'})
            self.assertEqual(response.status_code, 401, name)

    def test_cannot_analyze_other_users_recording(self):
        Recording.objects.create(room_sid='RM_OTHER', audio_url='https://example.com/a.wav',
                                 duration=1, user=self.other, transcript='secret')
        for name in ['generate_audio', 'analyze_pronunciation']:
            response = self.client.post(reverse(f'conversation_analysis:{name}'), {'room_sid': 'RM_OTHER'})
            self.assertEqual(response.status_code, 404, name)

        response = self.client.get(reverse('conversation_analysis:audio_analysis'), {'room_sid': 'RM_OTHER'})
        self.assertEqual(response.status_code, 404)

    def test_get_audio_file_requires_file_generated_in_session(self):
        Path(self.tmp.name, 'reference_x.wav').write_bytes(b'RIFF')
        url = reverse('conversation_analysis:get_audio_file', args=['reference_x.wav'])

        with override_settings(TEMP_AUDIO_DIR=self.tmp.name):
            self.assertEqual(self.client.get(url).status_code, 404)

            session = self.client.session
            session[AUDIO_FILES_SESSION_KEY] = ['reference_x.wav']
            session.save()
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'RIFF')

    def test_audio_analysis_page_escapes_transcript_for_javascript(self):
        Recording.objects.create(room_sid='RM_MINE', audio_url='https://example.com/a.wav',
                                 duration=1, user=self.user, transcript='</script><script>alert(1)</script>')
        response = self.client.get(reverse('conversation_analysis:audio_analysis'), {'room_sid': 'RM_MINE'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<script>alert(1)</script>')


class VocabularyDiversityTests(TestCase):
    def test_repetitive_text_has_lower_mtld(self):
        analyzer = VocabularyDiversityAnalyzer.__new__(VocabularyDiversityAnalyzer)  # NLTK のダウンロードを避ける
        repetitive = ['the', 'cat'] * 50
        varied = [f'word{i}' for i in range(100)]
        self.assertLess(analyzer.calculate_mtld(repetitive), analyzer.calculate_mtld(varied))
        self.assertEqual(analyzer.calculate_mtld([]), 0.0)


@skipUnless(HAS_LIBROSA, 'librosa is not installed')
class PronunciationAlignmentTests(TestCase):
    def test_skipped_word_does_not_shift_alignment(self):
        from .service_audio import PronunciationAnalysisSystem, WordSegment

        def segs(words):
            return [WordSegment(text=w, start=i, end=i + 0.5, confidence=1.0) for i, w in enumerate(words)]

        reference = segs(['I', 'like', 'green', 'apples.'])
        student = segs(['I', 'like', 'apples'])  # "green" を抜かした

        pairs = PronunciationAnalysisSystem.align_segments(student, reference)

        self.assertEqual([(s.text, r.text) for s, r in pairs],
                         [('I', 'I'), ('like', 'like'), ('apples', 'apples.')])

    def test_misrecognized_word_is_still_compared(self):
        from .service_audio import PronunciationAnalysisSystem, WordSegment

        def segs(words):
            return [WordSegment(text=w, start=i, end=i + 0.5, confidence=1.0) for i, w in enumerate(words)]

        reference = segs(['I', 'like', 'rice'])
        student = segs(['I', 'like', 'lice'])  # 発音の誤りで別の単語として聞き取られた

        pairs = PronunciationAnalysisSystem.align_segments(student, reference)

        self.assertIn(('lice', 'rice'), [(s.text, r.text) for s, r in pairs])

    def test_extra_word_next_to_misrecognized_word(self):
        from .service_audio import PronunciationAnalysisSystem, WordSegment

        def segs(words):
            return [WordSegment(text=w, start=i, end=i + 0.5, confidence=1.0) for i, w in enumerate(words)]

        reference = segs(['I', 'like', 'apples.'])
        student = segs(['I', 'like', 'apple', 'um'])

        pairs = PronunciationAnalysisSystem.align_segments(student, reference)

        self.assertEqual([(s.text, r.text) for s, r in pairs],
                         [('I', 'I'), ('like', 'like'), ('apple', 'apples.')])

    def test_similarity_is_between_zero_and_one(self):
        from .service_audio import PronunciationAnalysisSystem

        self.assertEqual(PronunciationAnalysisSystem.similarity_from_distance(0), 1.0)
        self.assertAlmostEqual(PronunciationAnalysisSystem.similarity_from_distance(150), 0.85)
        self.assertEqual(PronunciationAnalysisSystem.similarity_from_distance(10_000), 0.0)
