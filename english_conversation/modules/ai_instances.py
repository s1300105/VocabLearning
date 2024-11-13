import os
import json
import websockets
import asyncio
from dotenv import load_dotenv
import base64
import logger

load_dotenv()

class AIInstance:
    def __init__(self, role, system_message):
        self.api_key=os.getenv("OPENAI_API_KEY")
        self.role=role
        self.system_message=system_message
        self.ws_connection=None
    
    async def connect(self):
        """OpenAI APIへの接続を確立"""
        self.ws_connection=await websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            extra_headers={
                "Authorization":f"Bearer {self.api_key}",
                "OpenAI-Beta":"realtime=v1"
            }
        )
        await self.initialize_session()

    async def initialize_session(self):
        """セッションの初期化"""
        session_config={
            "type":"session.update",
            "session":{
                "instructions":self.system_message,
                "temperature":0.3
            }
        }
        await self.ws_connection.send(json.dumps(session_config))

    async def process_audio(self, audio_data, context=None):
        """音声データの処理"""
        try:
            # バイナリデータをbase64エンコード
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            request = {
                "type": "input_audio_buffer.append",
                "audio": audio_base64,
                "metadata": {
                    "session": {
                        "instructions": self.system_message,
                        "temperature": 0.3
                    }
                }
            }
            
            await self.ws_connection.send(json.dumps(request))
            
            # レスポンスの受信と処理
            response = await self.ws_connection.recv()
            return json.loads(response)
            
        except Exception as e:
            print(f"Error processing audio in AIInstance: {str(e)}")
            raise
    
    async def generate_feedback(self, text, context=None):
        """フィードバックの生成"""
        request={
            "type":"text.completion",
            "text":text,
            "context":context
        }
        await self.ws_connection.send(json.dumps(request))
        response=await self.ws_connection.recv()
        print(response)
        return json.loads(response)
    
class AIManager:
    def __init__(self):
        self.grammar_ai = AIInstance("grammar", GRAMMAR_SYSTEM_MESSAGE)
        self.conversation_ai = AIInstance("conversation", CONVERSATION_SYSTEM_MESSAGE)
        self.analysis_ai = AIInstance("analysis", ANALYSIS_SYSTEM_MESSAGE)
    
    async def initialize(self):
        """全AIインスタンスの初期化"""
        await asyncio.gather(
            self.grammar_ai.connect(),
            self.conversation_ai.connect(),
            self.analysis_ai.connect()
        )
    async def process_input(self, audio_data, context=None):
        """"入力の処理"""
        results = await asyncio.gather(
            self.grammar_ai.process_audio(audio_data),
            self.analysis_ai.process_audio(audio_data)
        )

        return {
            "grammar_analysis":results[0],
            "speech_analysis":results[1]
        }
    
    async def process_audio(self, audio_data, context=None):
        """音声データを処理"""
        try:
            # 音声認識と分析
            results = await asyncio.gather(
                self.grammar_ai.process_audio(audio_data),
                self.analysis_ai.process_audio(audio_data)
            )
            
            return {
                'grammar_analysis': results[0],
                'speech_analysis': results[1]
            }
        
        except Exception as e:
            logger.error(f"Error in AIManager.process_audio: {str(e)}")
            raise
    

        


# システムメッセージの定義
GRAMMAR_SYSTEM_MESSAGE = """
You are an English grammar correction specialist. Focus on:
1. Real-time grammar correction
2. Identifying common errors
3. Providing clear, concise corrections
"""

CONVERSATION_SYSTEM_MESSAGE = """
You are an English conversation assistant. Your role is to:
1. Help maintain natural conversation flow
2. Suggest appropriate phrases when needed
3. Provide context-appropriate responses
"""

ANALYSIS_SYSTEM_MESSAGE = """
You are a speech pattern analyzer. Focus on:
1. Detecting hesitation patterns
2. Analyzing fluency and confidence
3. Identifying areas needing improvement
"""