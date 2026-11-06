"""発音チェックで使う音声ファイルの用意（学習者の録音の取得と、お手本音声の生成）。

採点そのものは conversation_analysis.pronunciation（ローカルの音素認識モデル）で行う。
お手本音声（OpenAI TTS）は「お手本を聞く」ためだけに使い、採点には使わない。
"""
import hashlib
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache
from pydub import AudioSegment

from video_chat.views import get_room_recordings

logger = logging.getLogger(__name__)


class PronunciationAnalysisSystem:
    def __init__(self, openai_api_key: Optional[str] = None):
        self.openai_api_key = openai_api_key
        self._client = None
        self.temp_dir = Path(settings.TEMP_AUDIO_DIR)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._active_files = set()  # 現在使用中のファイルを追跡

    @property
    def client(self):
        # 録音の取得だけなら API キーは不要なので、お手本音声を作るときに初めて用意する
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.openai_api_key)
        return self._client

    def _cleanup_file(self, file_path: str) -> None:
        """安全にファイルを削除"""
        try:
            file_path = Path(file_path)
            if file_path.exists() and str(file_path) in self._active_files:
                file_path.unlink()
                self._active_files.remove(str(file_path))
        except Exception as e:
            logger.error(f"Error cleaning up file {file_path}: {e}")

    def generate_reference_audio(self, text: str) -> str:
        """OpenAI TTSを使用して参照音声を生成"""
        try:
            # 一時ファイルのパスを生成
            # hash() はプロセスごとに値が変わるので、安定したハッシュを使う
            digest = hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]
            temp_file = self.temp_dir / f"reference_{digest}.mp3"
            wav_file = temp_file.with_suffix('.wav')
            
            # 既存のファイルがあれば削除
            if temp_file.exists():
                temp_file.unlink()
            if wav_file.exists():
                wav_file.unlink()

            # OpenAI TTSで音声を生成
            response = self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text
            )

            # 音声データを保存
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # MP3をWAVに変換
            audio = AudioSegment.from_mp3(str(temp_file))
            audio.export(
                str(wav_file), 
                format='wav',
                parameters=["-ac", "1"]
            )
                
            # MP3ファイルを削除
            if temp_file.exists():
                temp_file.unlink()
                
            # ファイルを追跡リストに追加
            self._active_files.add(str(wav_file))
            logger.info(f"Generated reference audio: {wav_file}")
            return str(wav_file)
                
        except Exception as e:
            logger.error(f"Error generating reference audio: {e}")
            self._cleanup_file(temp_file)
            self._cleanup_file(wav_file)
            raise

    def get_room_recording(self, room_sid: str, local_audio_path: Optional[str] = None) -> str:
        """録音データを取得して作業ディレクトリに WAV ファイルとして保存

        local_audio_path が指定された場合（一人用レッスン）は、Twilio からではなく
        サーバーに保存済みの WAV（16kHz モノラル）をコピーして使う。
        """
        if local_audio_path:
            wav_file = self.temp_dir / f"recording_{room_sid}.wav"
            shutil.copyfile(local_audio_path, wav_file)
            logger.info(f"Using saved solo recording: {wav_file}")
            return str(wav_file)

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
            response = requests.get(latest_audio['url'], stream=True, timeout=60)
            if response.status_code != 200:
                raise Exception(f"Failed to download audio: {response.status_code}")

            # 音声データをチャンク単位でダウンロードして保存
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # WebMをWAVに変換
            wav_file = temp_file.with_suffix('.wav')
            
            try:
                result = subprocess.run([
                    'ffmpeg',
                    '-y',
                    '-i', str(temp_file),
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',  # Whisper用に16kHzに統一
                    '-ac', '1',
                    str(wav_file)
                ], capture_output=True, text=True)
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg conversion error: {result.stderr}")
                    raise Exception("Failed to convert audio file")
                    
            except Exception as conv_error:
                logger.error(f"Conversion error details: {str(conv_error)}")
                if wav_file.exists():
                    wav_file.unlink()
                raise conv_error

            if temp_file.exists():
                temp_file.unlink()
                    
            logger.info(f"Retrieved room recording: {wav_file}")
            return str(wav_file)
                    
        except Exception as e:
            logger.error(f"Error getting room recording: {e}")
            if 'temp_file' in locals() and temp_file.exists():
                temp_file.unlink()
            if 'wav_file' in locals() and wav_file.exists():
                wav_file.unlink()
            raise
