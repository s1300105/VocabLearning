import difflib
import hashlib
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import librosa
import numpy as np
import requests
from django.conf import settings
from django.core.cache import cache
from openai import OpenAI
from pydub import AudioSegment
from scipy.spatial.distance import cdist

from video_chat.views import get_room_recordings

logger = logging.getLogger(__name__)

# MFCC 距離 → 類似度 (0〜1) への換算スケール。
# similarity = 1 - distance / MFCC_DISTANCE_SCALE （経験的な値なので、実データで要調整）
MFCC_DISTANCE_SCALE = 1000.0
# これより短い区間は MFCC が安定しないので比較しない（16kHz で約 0.03 秒）
MIN_SEGMENT_SAMPLES = 512


def _normalize_word(text: str) -> str:
    return re.sub(r"[^a-z0-9']", '', text.lower())

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
        self.temp_dir = Path(settings.TEMP_AUDIO_DIR)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
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
            
            if word_comparisons:
                overall_score = float(np.mean([comp['similarity'] for comp in word_comparisons]))
            else:
                overall_score = 0.0
            
            return {
                'text': text,
                'score': overall_score,
                'word_comparisons': word_comparisons,
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



    @staticmethod
    def align_segments(student_segments: List[WordSegment],
                       reference_segments: List[WordSegment]) -> List[tuple]:
        """単語のテキストで学習者と参照音声を対応付ける。

        単純に先頭から zip すると、学習者が1語でも抜かしたり付け足したりした時点で
        以降がすべてずれるため、difflib で対応を取る。
        - 一致した単語は組にする
        - 同じ語数どうしの置き換え（例: "lice" が "rice" と聞き取られた）は
          発音の誤りの可能性が高いので、1対1で組にする
        - 語数が違う置き換えは、綴りが近い単語どうしだけを組にする
        - それ以外の抜けた単語・余分な単語は比較しない
        """
        student_words = [_normalize_word(seg.text) for seg in student_segments]
        reference_words = [_normalize_word(seg.text) for seg in reference_segments]
        matcher = difflib.SequenceMatcher(a=student_words, b=reference_words, autojunk=False)

        pairs = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
                index_pairs = zip(range(i1, i2), range(j1, j2))
            elif tag == 'replace':
                index_pairs = PronunciationAnalysisSystem._pair_similar_words(
                    student_words, range(i1, i2), reference_words, range(j1, j2))
            else:
                continue
            for i, j in index_pairs:
                if student_words[i] or reference_words[j]:
                    pairs.append((student_segments[i], reference_segments[j]))
        return pairs

    @staticmethod
    def _pair_similar_words(student_words, student_range, reference_words, reference_range,
                            min_ratio=0.5):
        """綴りの近さで単語を順番を保ったまま組にする（語数が違う置き換え区間用）"""
        index_pairs = []
        next_student = student_range.start
        for j in reference_range:
            best_i, best_ratio = None, min_ratio
            for i in range(next_student, student_range.stop):
                ratio = difflib.SequenceMatcher(a=student_words[i], b=reference_words[j]).ratio()
                if ratio >= best_ratio:
                    best_i, best_ratio = i, ratio
            if best_i is not None:
                index_pairs.append((best_i, j))
                next_student = best_i + 1
        return index_pairs

    @staticmethod
    def similarity_from_distance(distance: float) -> float:
        return float(max(0.0, min(1.0, 1.0 - distance / MFCC_DISTANCE_SCALE)))

    def compare_pronunciations(self, student_segments: List[WordSegment],
                               reference_segments: List[WordSegment],
                               student_audio: np.ndarray,
                               reference_audio: np.ndarray) -> List[Dict]:
        logger.info("Starting pronunciation comparison")
        pairs = self.align_segments(student_segments, reference_segments)
        logger.debug(
            f"Segments - Student: {len(student_segments)}, Reference: {len(reference_segments)}, "
            f"aligned: {len(pairs)}"
        )

        word_comparisons = []
        for student_seg, ref_seg in pairs:
            student_word = student_audio[int(student_seg.start * self.sample_rate):int(student_seg.end * self.sample_rate)]
            reference_word = reference_audio[int(ref_seg.start * self.sample_rate):int(ref_seg.end * self.sample_rate)]
            if len(student_word) < MIN_SEGMENT_SAMPLES or len(reference_word) < MIN_SEGMENT_SAMPLES:
                logger.debug(f"Skipping too short segment for '{ref_seg.text}'")
                continue

            student_mfcc = librosa.feature.mfcc(y=student_word, sr=self.sample_rate, n_mfcc=13)
            reference_mfcc = librosa.feature.mfcc(y=reference_word, sr=self.sample_rate, n_mfcc=13)

            # 学習者の各フレームについて、参照音声で最も近いフレームとの距離の平均
            # （DTW ではなく最近傍距離による簡易的な比較）
            distance_matrix = cdist(student_mfcc.T, reference_mfcc.T, metric='euclidean')
            distance = float(distance_matrix.min(axis=1).mean())

            word_comparisons.append({
                'word': ref_seg.text,
                'difference_score': distance,
                'similarity': self.similarity_from_distance(distance),
                'confidence': ref_seg.confidence,
                'start_time': ref_seg.start,       # 参照音声の時間
                'end_time': ref_seg.end,
                'student_start': student_seg.start,
                'student_end': student_seg.end,
                'duration_difference': (student_seg.end - student_seg.start) - (ref_seg.end - ref_seg.start),
            })

        word_comparisons.sort(key=lambda x: x['difference_score'], reverse=True)
        logger.info(f"Completed comparison of {len(word_comparisons)} words")
        return word_comparisons
