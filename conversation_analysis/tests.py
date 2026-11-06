import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from video_chat.models import Recording

from .views import AUDIO_FILES_SESSION_KEY
from .vocab_diversity_analysis import VocabularyDiversityAnalyzer

User = get_user_model()


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


class PronunciationViewTests(TestCase):
    """発音チェックの API（採点エンジン自体は test_pronunciation.py でテストする）"""

    def setUp(self):
        self.user = User.objects.create_user(email='me@example.com', password='pass-12345', username='me')
        self.client.force_login(self.user)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def make_read_aloud(self):
        recording = Recording.objects.create(
            lesson_type=Recording.LESSON_TYPE_SOLO, room_sid='SOLOabc', duration=3,
            user=self.user, reference_text='I like rice.', status='transcribed',
        )
        recording.audio_file.name = 'solo_recordings/2026/11/abc.wav'
        recording.save()
        return recording

    def test_read_aloud_page_works_without_transcript(self):
        self.make_read_aloud()
        response = self.client.get(reverse('conversation_analysis:audio_analysis'), {'room_sid': 'SOLOabc'})
        self.assertContains(response, 'I like rice.')
        self.assertContains(response, 'Sentence you read')

    def test_analyze_uses_reference_text_and_saved_file(self):
        from unittest import mock

        recording = self.make_read_aloud()
        audio_service = mock.Mock()
        audio_service.get_room_recording.return_value = str(Path(self.tmp.name, 'recording_SOLOabc.wav'))
        assessor = mock.Mock()
        assessor.assess_file.return_value = {'score': 88, 'words': [], 'issues': []}

        with mock.patch('conversation_analysis.views._audio_service', return_value=audio_service), \
                mock.patch('conversation_analysis.pronunciation.assessor.get_assessor', return_value=assessor):
            response = self.client.post(reverse('conversation_analysis:analyze_pronunciation'), {'room_sid': 'SOLOabc'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['score'], 88)
        audio_service.get_room_recording.assert_called_once_with(
            'SOLOabc', local_audio_path=recording.audio_file.path)
        assessor.assess_file.assert_called_once_with(
            audio_service.get_room_recording.return_value, 'I like rice.')
        # 再生用 URL が返り、そのファイルはこのセッションで取得できる
        self.assertEqual(response.json()['learner_audio_url'],
                         reverse('conversation_analysis:get_audio_file', args=['recording_SOLOabc.wav']))
        self.assertIn('recording_SOLOabc.wav', self.client.session[AUDIO_FILES_SESSION_KEY])

    def test_recording_that_does_not_match_text_returns_400(self):
        from unittest import mock

        self.make_read_aloud()
        assessor = mock.Mock()
        assessor.assess_file.side_effect = ValueError('The audio is too short for the expected text.')
        with mock.patch('conversation_analysis.views._audio_service'), \
                mock.patch('conversation_analysis.pronunciation.assessor.get_assessor', return_value=assessor):
            response = self.client.post(reverse('conversation_analysis:analyze_pronunciation'), {'room_sid': 'SOLOabc'})

        self.assertEqual(response.status_code, 400)
        self.assertNotIn('too short', response.json()['error'])

    def test_model_voice_needs_api_key(self):
        self.make_read_aloud()
        with override_settings(OPENAI_API_KEY=None):
            response = self.client.post(reverse('conversation_analysis:generate_audio'), {'room_sid': 'SOLOabc'})
        self.assertEqual(response.status_code, 503)

    def test_get_room_recording_copies_local_file(self):
        from .service_audio import PronunciationAnalysisSystem

        with override_settings(TEMP_AUDIO_DIR=self.tmp.name):
            source = Path(self.tmp.name, 'saved.wav')
            source.write_bytes(b'RIFFdata')
            path = PronunciationAnalysisSystem().get_room_recording('SOLOabc', local_audio_path=str(source))

            self.assertEqual(Path(path).name, 'recording_SOLOabc.wav')
            self.assertEqual(Path(path).read_bytes(), b'RIFFdata')
