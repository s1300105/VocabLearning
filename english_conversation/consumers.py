import json
import logging
import base64
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer

from .modules.conversation_manager import ConversationManager

logger = logging.getLogger(__name__)


class LessonConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        """WebSocket接続時の処理"""
        try:
            self.room_name = self.scope['url_route']['kwargs']['room_name']
            self.room_group_name = f'lesson_{self.room_name}'
            
            # 会話マネージャーの初期化
            self.conversation_manager = ConversationManager()
            logger.debug("Initializing conversation manager")
            await self.conversation_manager.initialize()
            
            # グループに参加
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # 接続を受け入れ
            await self.accept()
            
            # 初期メッセージを送信
            await self.send_json({
                'type': 'ai_feedback',
                'data': {
                    'type': 'greeting',
                    'content': 'Hello! I am your AI assistant. I will help you with your English conversation.'
                }
            })
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            raise

    
    async def receive_json(self, content):
        try:
            message_type = content.get('type')
            logger.debug(f"Received message type: {message_type}")

            if message_type == 'audio':
                logger.debug("Processing audio data")
                audio_base64 = content.get('audio')
                
                if not audio_base64:
                    raise ValueError("No audio data received")

                try:
                    # Base64デコード
                    audio_bytes = base64.b64decode(audio_base64)
                    
                    # 音声データの処理
                    result = await self.conversation_manager.process_audio_frame(
                        audio_bytes,
                        {'room_name': self.room_name}
                    )
                    
                    # 結果があれば送信
                    if result:
                        await self.send_json({
                            'type': 'ai_feedback',
                            'data': result
                        })
                        
                except Exception as e:
                    logger.error(f"Audio processing error: {str(e)}")
                    await self.send_json({
                        'type': 'error',
                        'message': f'Audio processing error: {str(e)}'
                    })
                    
        except Exception as e:
            logger.error(f"Error in receive_json: {str(e)}")
            await self.send_json({
                'type': 'error',
                'message': f'Internal error: {str(e)}'
            })


    async def disconnect(self, close_code):
        """WebSocket切断時の処理"""
        try:
            #if hasattr(self, 'conversation_manager'):
               # await self.conversation_manager.cleanup()
                
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")
