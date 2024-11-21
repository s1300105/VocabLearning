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
import tempfile
import json

logger = logging.getLogger(__name__)

@dataclass
class WordSegment:
    text: str
    start: float
    end: float
    confidence: float

class PronunciationAnalysisSystem:
    def __init__(self, openai_api_key: str):
        """
        発音分析システムの初期化
        """
        self.client = OpenAI(api_key=openai_api_key)
        self.sample_rate = 16000
        self.temp_dir = Path("temp_audio")
        self.temp_dir.mkdir(exist_ok=True)
        self._active_files = set()  # 現在使用中のファイルを追跡

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
            temp_file = self.temp_dir / f"reference_{hash(text)}.mp3"
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

    def analyze_pronunciation(self, room_sid: str, text: str) -> Dict:
        """
        発音分析を実行
        """
        student_audio_path = None
        reference_audio_path = None
        
        try:
            student_audio_path = self.get_room_recording(room_sid)
            self._active_files.add(student_audio_path)
            student_audio, _ = librosa.load(student_audio_path, sr=self.sample_rate)
            
            reference_audio_path = self.generate_reference_audio(text)
            reference_audio, _ = librosa.load(reference_audio_path, sr=self.sample_rate)
            
            # Whisper APIを使用して単語セグメンテーション
            student_segments = self.get_word_segments(student_audio_path)
            reference_segments = self.get_word_segments(reference_audio_path)
            
            word_comparisons = self.compare_pronunciations(
                student_segments,
                reference_segments,
                student_audio,
                reference_audio
            )

            for comp in word_comparisons:
                logger.debug(f"Word: {comp['word']}, Start: {comp['start_time']}, End: {comp['end_time']}")
            
            # 文の区切りを分析
            sentence_boundaries = []
            current_sentence = {'start': None, 'end': None, 'words': []}
            
            for i, segment in enumerate(reference_segments):
                word_info = {
                    'text': segment.text,
                    'start': segment.start,
                    'end': segment.end,
                }
                
                if current_sentence['start'] is None:
                    current_sentence['start'] = segment.start
                
                current_sentence['words'].append(word_info)
                
                # 文の終わりを検出（ピリオド、疑問符、感嘆符）
                if segment.text.strip().endswith(('.', '?', '!')):
                    current_sentence['end'] = segment.end
                    sentence_boundaries.append(current_sentence)
                    current_sentence = {'start': None, 'end': None, 'words': []}
                    
            # 最後の文が残っている場合は追加
            if current_sentence['words'] and current_sentence['start'] is not None:
                current_sentence['end'] = current_sentence['words'][-1]['end']
                sentence_boundaries.append(current_sentence)
            
            overall_score = 1.0 - np.mean([comp['difference_score'] for comp in word_comparisons])
            overall_score = max(0, min(1, overall_score))
            
            return {
                'text': text,
                'score': overall_score,
                'word_comparisons': word_comparisons[:5],
                'sentence_boundaries': sentence_boundaries,  # 追加
                'audio_paths': {
                    'student': student_audio_path,
                    'reference': reference_audio_path
                }
            }
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
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
            response = requests.get(latest_audio['url'], stream=True)
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
                import subprocess
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

    def get_word_segments(self, audio_path: str) -> List[WordSegment]:
        logger.info(f"Starting word segmentation for audio file: {audio_path}")
        try:
            with open(audio_path, 'rb') as audio_file:
                logger.debug("Sending request to Whisper API")
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
                
            # responseをdictに変換
            if hasattr(response, 'model_dump'):
                result = response.model_dump()
            else:
                result = response
                
            logger.debug(f"Response type: {type(result)}")

            segments = []
            if 'words' in result:
                logger.debug(f"Processing {len(result['words'])} direct words")
                for word_info in result['words']:
                    segment = WordSegment(
                        text=word_info["word"].strip(),
                        start=float(word_info["start"]),
                        end=float(word_info["end"]),
                        confidence=float(word_info.get("probability", 0.9))
                    )
                    segments.append(segment)
            elif 'segments' in result:
                logger.debug(f"Processing words from {len(result['segments'])} segments")
                for segment in result['segments']:
                    if 'words' in segment:
                        for word_info in segment['words']:
                            segment = WordSegment(
                                text=word_info["word"].strip(),
                                start=float(word_info["start"]),
                                end=float(word_info["end"]),
                                confidence=float(word_info.get("probability", 0.9))
                            )
                            segments.append(segment)

            logger.info(f"Successfully extracted {len(segments)} word segments")
            return segments
            
        except Exception as e:
            logger.error(f"Error in word segmentation: {e}", exc_info=True)
            raise



    def compare_pronunciations(self, student_segments: List[WordSegment], 
                             reference_segments: List[WordSegment], 
                             student_audio: np.ndarray, 
                             reference_audio: np.ndarray) -> List[Dict]:
        logger.info("Starting pronunciation comparison")
        logger.debug(f"Number of segments - Student: {len(student_segments)}, Reference: {len(reference_segments)}")
        
        word_comparisons = []
        
        for i, (student_seg, ref_seg) in enumerate(zip(student_segments, reference_segments)):
            logger.debug(f"Comparing word {i+1}: '{student_seg.text}' with reference '{ref_seg.text}'")
            
            # Extract audio segments
            student_start = int(student_seg.start * self.sample_rate)
            student_end = int(student_seg.end * self.sample_rate)
            ref_start = int(ref_seg.start * self.sample_rate)
            ref_end = int(ref_seg.end * self.sample_rate)
            
            logger.debug(f"Student segment timing: {student_start}-{student_end}")
            logger.debug(f"Reference segment timing: {ref_start}-{ref_end}")

            student_word = student_audio[student_start:student_end]
            reference_word = reference_audio[ref_start:ref_end]
            
            # Calculate MFCCs
            student_mfcc = librosa.feature.mfcc(y=student_word, sr=self.sample_rate, n_mfcc=13)
            reference_mfcc = librosa.feature.mfcc(y=reference_word, sr=self.sample_rate, n_mfcc=13)
            
            logger.debug(f"MFCC shapes - Student: {student_mfcc.shape}, Reference: {reference_mfcc.shape}")
            
            # Calculate DTW distance
            distance_matrix = cdist(student_mfcc.T, reference_mfcc.T, metric='euclidean')
            distance = distance_matrix.min(axis=1).mean()
            
            logger.debug(f"DTW distance for '{student_seg.text}': {distance}")
            
            # Store comparison results
            comparison = {
            'word': ref_seg.text,  # 参照音声から単語を取得
            'difference_score': distance,
            'confidence': ref_seg.confidence,
            'start_time': ref_seg.start,  # 参照音声の開始時間
            'end_time': ref_seg.end,      # 参照音声の終了時間
            'student_start': student_seg.start,  # 学習者の時間も保持
            'student_end': student_seg.end,
            'duration_difference': (student_seg.end - student_seg.start) - 
                                (ref_seg.end - ref_seg.start)
        }
            word_comparisons.append(comparison)
            logger.debug(f"Comparison result: {comparison}")
        
        word_comparisons.sort(key=lambda x: x['difference_score'], reverse=True)
        logger.info(f"Completed comparison of {len(word_comparisons)} words")
        logger.debug("Top 3 different pronunciations: " + 
                    ", ".join([f"{c['word']}({c['difference_score']:.2f})" 
                             for c in word_comparisons[:3]]))
        
        return word_comparisons