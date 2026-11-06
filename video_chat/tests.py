import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Recording

User = get_user_model()

VALID_SID = 'RT' + 'a' * 32


class VideoChatTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='me@example.com', password='pass-12345', username='me')
        self.other = User.objects.create_user(email='other@example.com', password='pass-12345', username='other')
        self.client.force_login(self.user)

    def make_recording(self, user, room_sid='RM1', transcript='hello world'):
        return Recording.objects.create(
            room_sid=room_sid, audio_url='https://example.com/a.wav', duration=10,
            user=user, transcript=transcript,
        )


class AuthenticationTests(TestCase):
    def test_json_apis_return_401_for_anonymous_users(self):
        for url, method in [
            (reverse('video_chat:make_token'), 'post'),
            (reverse('video_chat:recording_complete'), 'post'),
            (reverse('video_chat:go_transcribe'), 'post'),
            (reverse('video_chat:recording_status', args=[1]), 'get'),
        ]:
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 401, url)

    def test_pages_redirect_anonymous_users(self):
        for name in ['video_lesson', 'player', 'recording_list', 'transcribe_audio']:
            response = self.client.get(reverse(f'video_chat:{name}'))
            self.assertEqual(response.status_code, 302, name)


class CsrfTests(VideoChatTestBase):
    def test_recording_complete_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(
            reverse('video_chat:recording_complete'),
            data=json.dumps({'RoomSid': 'RM1'}), content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_go_transcribe_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(
            reverse('video_chat:go_transcribe'),
            data=json.dumps({'RoomSid': 'RM1'}), content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)


class TranscribeAudioTests(VideoChatTestBase):
    def test_path_traversal_is_rejected(self):
        for sid in ['../../mysite/settings', '..%2F..%2Fsecret', 'RT' + 'a' * 31 + '/']:
            response = self.client.get(reverse('video_chat:transcribe_audio'), {'sid': sid})
            self.assertEqual(response.status_code, 404, sid)

    def test_transcript_not_created_in_this_session_is_rejected(self):
        response = self.client.get(reverse('video_chat:transcribe_audio'), {'sid': VALID_SID})
        self.assertEqual(response.status_code, 404)


class RecordingAccessTests(VideoChatTestBase):
    def test_recording_status_of_other_user_is_not_found(self):
        recording = self.make_recording(self.other)
        response = self.client.get(reverse('video_chat:recording_status', args=[recording.id]))
        self.assertEqual(response.status_code, 404)

    def test_recording_status_of_own_recording(self):
        recording = self.make_recording(self.user)
        response = self.client.get(reverse('video_chat:recording_status', args=[recording.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['transcript'], 'hello world')

    def test_player_does_not_show_other_users_recording(self):
        self.make_recording(self.other, room_sid='RM_OTHER', transcript='secret')
        response = self.client.get(reverse('video_chat:player'), {'room_sid': 'RM_OTHER'})
        self.assertContains(response, 'Recording not found')
        self.assertNotContains(response, 'secret')

    def test_player_uses_saved_transcript_not_query_parameter(self):
        self.make_recording(self.user, room_sid='RM_MINE', transcript='saved transcript')
        media = [{'url': 'https://example.com/a.wav', 'duration': 3, 'sid': VALID_SID,
                  'type': 'audio', 'status': 'completed', 'created_at': '2024-01-01T00:00:00'}]
        with mock.patch('video_chat.views.get_room_recordings', return_value=media):
            response = self.client.get(reverse('video_chat:player'),
                                       {'room_sid': 'RM_MINE', 'transcript': '<script>alert(1)</script>'})

        self.assertContains(response, 'saved transcript')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_recording_list_shows_only_own_recordings(self):
        self.make_recording(self.user, room_sid='RM_MINE')
        self.make_recording(self.other, room_sid='RM_OTHER')
        response = self.client.get(reverse('video_chat:recording_list'))
        self.assertContains(response, 'RM_MINE')
        self.assertNotContains(response, 'RM_OTHER')

    def test_recording_complete_saves_recording_for_current_user(self):
        media = [{'url': 'https://example.com/a.wav', 'duration': 3, 'sid': VALID_SID,
                  'type': 'audio', 'status': 'completed', 'created_at': '2024-01-01T00:00:00'}]
        with mock.patch('video_chat.views.get_room_recordings', return_value=media), \
                mock.patch('video_chat.services.AudioTranscriptionService.transcribe_audio', return_value='hi there'), \
                mock.patch('video_chat.services.OpenAI'):
            response = self.client.post(
                reverse('video_chat:recording_complete'),
                data=json.dumps({'RoomSid': 'RM_NEW'}), content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        recording = Recording.objects.get(room_sid='RM_NEW')
        self.assertEqual(recording.user, self.user)
        self.assertEqual(recording.transcript, 'hi there')


class MakeTokenTests(VideoChatTestBase):
    def test_invalid_room_name_is_rejected(self):
        response = self.client.post(
            reverse('video_chat:make_token'),
            data=json.dumps({'room_name': '../x', 'user_type': 'student'}), content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_json_is_rejected(self):
        response = self.client.post(reverse('video_chat:make_token'), data='{', content_type='application/json')
        self.assertEqual(response.status_code, 400)


def make_wav_bytes(seconds=3.0, sample_rate=44100):
    """テスト用の正弦波 WAV（ステレオ 44.1kHz → サーバーで 16kHz モノラルに変換される）"""
    import io
    import math
    import struct
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(int(seconds * sample_rate)):
            value = int(8000 * math.sin(2 * math.pi * 440 * i / sample_rate))
            frames += struct.pack('<hh', value, value)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


class SoloLessonTestBase(VideoChatTestBase):
    def setUp(self):
        super().setUp()
        import shutil
        import tempfile

        from django.test import override_settings

        self.private_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.private_dir, ignore_errors=True)
        settings_override = override_settings(PRIVATE_MEDIA_ROOT=self.private_dir)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def upload(self, content, name='recording.wav', topic='Talk about your family.', client=None, mode='talk'):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return (client or self.client).post(reverse('video_chat:solo_upload'), {
            'audio': SimpleUploadedFile(name, content, content_type='audio/wav'),
            'prompt': topic,
            'mode': mode,
        })

    def create_solo_recording(self, user):
        with mock.patch('video_chat.services.AudioTranscriptionService.transcribe_file', return_value='hello'):
            from .services import SoloRecordingService
            from django.core.files.uploadedfile import SimpleUploadedFile

            return SoloRecordingService().create_recording(
                user, SimpleUploadedFile('r.wav', make_wav_bytes()), topic='t')


class SoloLessonPageTests(SoloLessonTestBase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('video_chat:solo_lesson'))
        self.assertEqual(response.status_code, 302)

    def test_shows_topic_for_users_level(self):
        from .topics import SOLO_TOPICS

        self.user.cefr = 'A1'
        self.user.save()
        response = self.client.get(reverse('video_chat:solo_lesson'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['mode'], 'talk')
        self.assertIn(response.context['prompt'], SOLO_TOPICS['A1'])

    def test_read_aloud_mode_shows_sentence(self):
        from .topics import READ_ALOUD_SENTENCES

        self.user.cefr = 'A2'
        self.user.save()
        response = self.client.get(reverse('video_chat:solo_lesson'), {'mode': 'read'})

        self.assertEqual(response.context['mode'], 'read')
        self.assertIn(response.context['prompt'], READ_ALOUD_SENTENCES['A2'])
        self.assertContains(response, 'Read this sentence')

    def test_another_topic_avoids_previous_one(self):
        from .topics import random_topic

        previous = random_topic('B1')
        self.assertTrue(all(random_topic('B1', exclude=previous) != previous for _ in range(20)))


class SoloUploadTests(SoloLessonTestBase):
    def test_anonymous_user_gets_401(self):
        self.client.logout()
        self.assertEqual(self.upload(make_wav_bytes()).status_code, 401)

    def test_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(self.upload(make_wav_bytes(), client=client).status_code, 403)

    def test_missing_file_is_rejected(self):
        response = self.client.post(reverse('video_chat:solo_upload'), {'topic': 'x'})
        self.assertEqual(response.status_code, 400)

    def test_non_audio_file_is_rejected(self):
        response = self.upload(b'this is not audio', name='recording.webm')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Recording.objects.exists())

    def test_too_short_recording_is_rejected(self):
        response = self.upload(make_wav_bytes(seconds=0.5))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Recording.objects.exists())

    def test_upload_saves_converted_recording_and_transcript(self):
        with mock.patch('video_chat.services.AudioTranscriptionService.transcribe_file',
                        return_value='My family has four people.') as transcribe:
            response = self.upload(make_wav_bytes(seconds=3))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        recording = Recording.objects.get(id=data['recording_id'])
        self.assertTrue(recording.is_solo)
        self.assertEqual(recording.user, self.user)
        self.assertEqual(recording.status, 'transcribed')
        self.assertEqual(recording.transcript, 'My family has four people.')
        self.assertEqual(recording.topic, 'Talk about your family.')
        self.assertEqual(recording.duration, 3)
        self.assertTrue(recording.room_sid.startswith(Recording.SOLO_ROOM_SID_PREFIX))
        self.assertIn(recording.room_sid, data['player_url'])
        transcribe.assert_called_once()

        # 公開されない場所に 16kHz モノラルの WAV として保存される
        import wave
        from pathlib import Path

        saved = Path(recording.audio_file.path)
        self.assertTrue(saved.is_relative_to(self.private_dir))
        with wave.open(str(saved)) as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getframerate(), 16000)

    def test_read_aloud_upload_skips_transcription(self):
        with mock.patch('video_chat.services.AudioTranscriptionService.transcribe_file') as transcribe:
            response = self.upload(make_wav_bytes(), topic='I really like rice.', mode='read')

        self.assertEqual(response.status_code, 200)
        transcribe.assert_not_called()  # 正解の文が分かっているので外部 API は使わない
        recording = Recording.objects.get()
        self.assertTrue(recording.is_read_aloud)
        self.assertEqual(recording.reference_text, 'I really like rice.')
        self.assertEqual(recording.topic, '')
        self.assertEqual(recording.pronunciation_text, 'I really like rice.')
        self.assertEqual(recording.status, 'transcribed')
        self.assertIn(reverse('conversation_analysis:audio_analysis'), response.json()['next_url'])

    def test_read_aloud_without_sentence_is_rejected(self):
        response = self.upload(make_wav_bytes(), topic='', mode='read')
        self.assertEqual(response.status_code, 400)

    def test_transcription_failure_marks_recording_failed(self):
        with mock.patch('video_chat.services.AudioTranscriptionService.transcribe_file',
                        side_effect=RuntimeError('whisper down')):
            response = self.upload(make_wav_bytes())

        self.assertEqual(response.status_code, 500)
        self.assertNotIn('whisper down', response.content.decode())
        self.assertEqual(Recording.objects.get().status, 'failed')


class SoloPlaybackTests(SoloLessonTestBase):
    def test_owner_can_download_audio(self):
        recording = self.create_solo_recording(self.user)
        response = self.client.get(reverse('video_chat:solo_audio', args=[recording.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'audio/wav')
        self.assertTrue(b''.join(response.streaming_content).startswith(b'RIFF'))

    def test_other_user_cannot_download_audio(self):
        recording = self.create_solo_recording(self.other)
        response = self.client.get(reverse('video_chat:solo_audio', args=[recording.id]))
        self.assertEqual(response.status_code, 404)

    def test_player_uses_saved_audio_without_twilio(self):
        recording = self.create_solo_recording(self.user)
        with mock.patch('video_chat.views.get_room_recordings', side_effect=AssertionError('Twilio called')):
            response = self.client.get(reverse('video_chat:player'), {'room_sid': recording.room_sid})

        self.assertEqual(response.status_code, 200)
        recordings = json.loads(response.context['recordings_json'])
        self.assertEqual(recordings[0]['url'], reverse('video_chat:solo_audio', args=[recording.id]))
        self.assertContains(response, 'Topic:')

    def test_recording_list_shows_solo_recordings(self):
        self.create_solo_recording(self.user)
        response = self.client.get(reverse('video_chat:recording_list'))
        self.assertContains(response, 'Solo practice')
