
import logging
import asyncio
from .ai_instances import AIManager
from .silence_analyzer import SilenceAnalyzer
from .hesitation_detector import HesitationDetector

logger = logging.getLogger(__name__)

class ConversationManager:
    def __init__(self):
        self.ai_manager = None
        self.silence_analyzer = None
        self.hesitation_detector = None
        self.is_initialized = False
        self.active_session = None

    async def initialize(self):
        """初期化処理"""
        try:
            self.ai_manager = AIManager()
            self.silence_analyzer = SilenceAnalyzer()
            self.hesitation_detector = HesitationDetector()
            
            # AIManagerの初期化
            await self.ai_manager.initialize()
            
            self.is_initialized = True
            logger.info("ConversationManager initialized successfully")
            
            # 新しいセッションの開始
            self.active_session = {
                'id': str(asyncio.get_event_loop().time()),
                'history': [],
                'metrics': {
                    'silence_patterns': [],
                    'hesitation_patterns': [],
                    'grammar_corrections': []
                }
            }
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing ConversationManager: {str(e)}")
            raise

    async def process_audio_frame(self, audio_data, metadata):
        """音声フレームの処理"""
        if not self.is_initialized or not self.active_session:
            logger.error("No active session")
            raise ValueError("No active session")

        try:
            # 沈黙の分析
            silence_info = self.silence_analyzer.process_audio(audio_data)
            
            # 音声が検出された場合
            if not silence_info['is_silent']:
                # 音声の処理と分析
                analysis_result = await self.ai_manager.process_audio(audio_data)
                
                if analysis_result:
                    # 躊躇の検出
                    hesitation_info = self.hesitation_detector.analyze_speech(
                        analysis_result.get('text', ''),
                        {'silence_info': silence_info}
                    )
                    
                    # 結果の保存
                    self.active_session['history'].append({
                        'type': 'speech',
                        'text': analysis_result.get('text', ''),
                        'analysis': analysis_result.get('analysis', {}),
                        'hesitation': hesitation_info
                    })
                    
                    return {
                        'type': 'analysis',
                        'content': {
                            'text': analysis_result.get('text', ''),
                            'analysis': analysis_result.get('analysis', {}),
                            'suggestions': await self.generate_suggestions(analysis_result)
                        }
                    }
            
            # 長い沈黙の場合
            elif silence_info['silence_duration'] > 3.0:
                return {
                    'type': 'suggestion',
                    'content': 'Would you like to try expressing that in a different way?'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing audio frame: {str(e)}")
            raise

    async def process_text(self, text):
        """テキストメッセージの処理"""
        if not self.is_initialized or not self.active_session:
            logger.error("No active session")
            raise ValueError("No active session")

        try:
            result = await self.ai_manager.process_text(text)
            
            if result:
                self.active_session['history'].append({
                    'type': 'text',
                    'content': text,
                    'response': result
                })
                
            return result
            
        except Exception as e:
            logger.error(f"Error processing text: {str(e)}")
            raise

    async def generate_suggestions(self, analysis_result):
        """提案の生成"""
        if not self.is_initialized or not self.active_session:
            return []

        try:
            return await self.ai_manager.generate_suggestions({
                'text': analysis_result.get('text', ''),
                'analysis': analysis_result.get('analysis', {})
            })
        except Exception as e:
            logger.error(f"Error generating suggestions: {str(e)}")
            return []

    async def end_session(self):
        """セッションの終了処理"""
        try:
            if self.active_session:
                summary = {
                    'session_id': self.active_session['id'],
                    'history_length': len(self.active_session['history']),
                    'metrics': self.active_session['metrics']
                }
                self.active_session = None
                return summary
                
        except Exception as e:
            logger.error(f"Error ending session: {str(e)}")
            raise

    async def cleanup(self):
        """クリーンアップ処理"""
        try:
            if self.active_session:
                await self.end_session()
            
            if self.ai_manager:
                await self.ai_manager.cleanup()
                
            self.is_initialized = False
            logger.info("ConversationManager cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            raise
