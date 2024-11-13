
import os
import json
import uuid
import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from channels.generic.websocket import AsyncWebsocketConsumer
from .modules.conversation_manager import ConversationManager
import twilio.jwt.access_token
import twilio.jwt.access_token.grants
from twilio.rest import Client
from django.conf import settings

logger = logging.getLogger(__name__)

# Twilioクライアントの初期化
try:
    twilio_client = Client(
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_SECRET,
        settings.TWILIO_ACCOUNT_SID
    )
except Exception as e:
    logger.error(f"Failed to initialize Twilio client: {str(e)}")
    twilio_client = None

class LessonConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """WebSocket接続の確立"""
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'lesson_{self.room_name}'
        self.conversation_manager = ConversationManager()
        
        await self.conversation_manager.initialize()
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        """WebSocket接続の終了"""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # セッションサマリーの生成
        summary = await self.conversation_manager.generate_session_summary()
        if summary:
            await self.send(text_data=json.dumps({
                'type': 'session_summary',
                'summary': summary
            }))

    async def receive(self, text_data):
        """メッセージの受信処理"""
        data = json.loads(text_data)
        
        if data['type'] == 'audio':
            # 音声データの処理
            result = await self.conversation_manager.process_audio_frame(
                data['audio'],
                {'room_name': self.room_name}
            )
            
            if result:
                await self.send(text_data=json.dumps({
                    'type': 'ai_feedback',
                    'data': result
                }))

def find_or_create_room(room_name):
    """既存のルームを探すか、新しいルームを作成"""
    if not twilio_client:
        raise Exception("Twilio client is not initialized")
        
    try:
        room = twilio_client.video.rooms(room_name).fetch()
        logger.info(f"Found existing room: {room_name}")
        return room
    except Exception as e:
        if hasattr(e, 'code') and e.code == 20404:  # Room not found
            room = twilio_client.video.rooms.create(
                unique_name=room_name,
                type="go",
                record_participants_on_connect=False
            )
            logger.info(f"Created new room: {room_name}")
            return room
        raise

def get_access_token(room_name, identity=None):
    """アクセストークンの生成"""
    if not all([
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_SECRET
    ]):
        raise ValueError("Twilio credentials are not properly configured")
        
    if identity is None:
        identity = str(uuid.uuid4().int)
    
    try:
        token = twilio.jwt.access_token.AccessToken(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_API_KEY_SID,
            settings.TWILIO_API_SECRET,
            identity=identity,
            ttl=3600  # 1時間
        )
        
        # ビデオグラントの追加
        grant = twilio.jwt.access_token.grants.VideoGrant(room=room_name)
        token.add_grant(grant)
        
        logger.debug(f"Generated access token for identity: {identity}")
        return token
        
    except Exception as e:
        logger.error(f"Failed to generate access token: {str(e)}")
        raise

@csrf_exempt
@require_http_methods(["POST"])
def generate_token(request):
    """Twilioトークンを生成するAPI"""
    try:
        data = json.loads(request.body)
        room_name = data.get('room_name')
        
        if not room_name:
            return JsonResponse({'error': 'Room name is required'}, status=400)
            
        if not room_name.isalnum():
            return JsonResponse({'error': 'Room name must be alphanumeric'}, status=400)
            
        # ルームの作成または取得
        room = find_or_create_room(room_name)
        
        # トークンの生成
        token = get_access_token(room_name)
        
        # JWT トークンの生成と変換
        jwt_token = token.to_jwt()
        if isinstance(jwt_token, bytes):
            jwt_token = jwt_token.decode('utf-8')
            
        return JsonResponse({
            'token': jwt_token,
            'room': {
                'name': room_name,
                'sid': room.sid,
                'status': room.status
            },
            'ws_url': f'/ws/lesson/{room_name}/'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON data'
        }, status=400)
        
    except Exception as e:
        logger.error(f"Error in generate_token: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error',
            'details': str(e)
        }, status=500)

def video_chat(request):
    """ビデオチャットページの表示"""
    return render(request, 'english_conversation/video_chat.html')
