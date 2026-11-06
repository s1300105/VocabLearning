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
