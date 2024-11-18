from IPython.display import Audio, display, HTML
import numpy as np
import base64
import librosa
from pydub import AudioSegment
from scipy.spatial.distance import cdist
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import matplotlib.pyplot as plt
from pathlib import Path
from openai import OpenAI
import logging
from dotenv import load_dotenv
import os
from video_chat.views import get_room_recordings
from django.conf import settings
from django.core.cache import cache
import requests


logger = logging.getLogger(__name__)


@dataclass
class WordSegment:
    text: str
    start: float
    end: float
    confidence: float
    phonemes: List[str]



class PronunciationAnalysisSystem:
    def __init__(self, openai_api_key: str):
        """
        発音分析システムの初期化
        """
        self.client = OpenAI(api_key=openai_api_key)
        self.sample_rate = 16000
        self.frame_length = 0.025
        self.frame_shift = 0.01
        self.temp_dir = Path("temp_audio")
        self.temp_dir.mkdir(exist_ok=True)


    def generate_reference_audio(self, text: str) -> str:
        """OpenAI TTSを使用して参照音声を生成"""
        try:
            # 一時ファイルのパスを生成
            temp_file = self.temp_dir / f"reference_{hash(text)}.mp3"
                
            # OpenAI TTSで音声を生成
            response = self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text
            )

            # 音声データをチャンク単位でダウンロードして保存
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # MP3をWAVに変換
            wav_file = temp_file.with_suffix('.wav')
            audio = AudioSegment.from_mp3(str(temp_file))
            audio.export(
                str(wav_file), 
                format='wav',
                parameters=["-ac", "1"]  # モノラルに変換
            )
                
            # MP3ファイルを削除
            if temp_file.exists():
                temp_file.unlink()
                
            logger.info(f"Generated reference audio: {wav_file}")
            return str(wav_file)
                
        except Exception as e:
            logger.error(f"Error generating reference audio: {e}")
            # エラー時の一時ファイルのクリーンアップ
            if 'temp_file' in locals() and temp_file.exists():
                temp_file.unlink()
            if 'wav_file' in locals() and wav_file.exists():
                wav_file.unlink()
            raise
    
    def get_room_recording(self, room_sid: str) -> str:
        """録音データを取得してWAVファイルとして保存"""
        try:
            media_files = cache.get(f'room_recordings_{room_sid}')

            if not media_files:
                media_files = get_room_recordings(room_sid)

            if not media_files:
                logger.warning(f"No recordings found for room {room_sid}")
                raise Exception("No recordings found for this room")

            audio_files = [f for f in media_files if f['type'] == 'audio']
            if not audio_files:
                raise Exception("No audio recordings found for this room")

            latest_audio = audio_files[0]
            logger.debug(f"Latest audio details: {latest_audio}")
                
            # 一時ファイルのパスを生成（.webmとして保存）
            temp_file = self.temp_dir / f"recording_{latest_audio['sid']}.webm"
            logger.debug(f"Temporary file path: {temp_file}")
                    
            # 音声ファイルをダウンロード
            logger.debug(f"Attempting to download from URL: {latest_audio['url']}")
            response = requests.get(latest_audio['url'], stream=True)
            logger.debug(f"Download response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")

            if response.status_code != 200:
                raise Exception(f"Failed to download audio: {response.status_code}")

            # 音声データをチャンク単位でダウンロードして保存
            file_size = 0
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file_size += len(chunk)
                        f.write(chunk)
            
            logger.debug(f"Downloaded file size: {file_size} bytes")

            # WebMをWAVに変換
            wav_file = temp_file.with_suffix('.wav')
            logger.debug(f"WAV file path: {wav_file}")
            
            try:
                # ffmpegを直接使用して変換
                import subprocess
                result = subprocess.run([
                    'ffmpeg',
                    '-i', str(temp_file),
                    '-acodec', 'pcm_s16le',  # PCM形式で出力
                    '-ar', '44100',          # サンプリングレートを44.1kHzに
                    '-ac', '1',              # モノラルに変換
                    str(wav_file)
                ], capture_output=True, text=True)
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg conversion error: {result.stderr}")
                    raise Exception("Failed to convert audio file")
                    
                logger.debug("Successfully converted to WAV format")
                    
            except Exception as conv_error:
                logger.error(f"Conversion error details: {str(conv_error)}")
                if wav_file.exists():
                    wav_file.unlink()
                raise conv_error

            # 一時ファイルを削除
            if temp_file.exists():
                temp_file.unlink()
                logger.debug("Temporary WebM file deleted")
                    
            logger.info(f"Retrieved room recording: {wav_file}")
            return str(wav_file)
                    
        except Exception as e:
            logger.error(f"Error getting room recording: {e}")
            if 'temp_file' in locals() and temp_file.exists():
                temp_file.unlink()
            if 'wav_file' in locals() and wav_file.exists():
                wav_file.unlink()
            raise