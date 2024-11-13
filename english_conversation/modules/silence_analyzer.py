
import time
import numpy as np
from collections import deque

class SilenceAnalyzer:
    def __init__(self):
        # 基本パラメータ
        self.last_speech_time = time.time()      # 最後に音声が検出された時刻
        self.silence_threshold = 0.01            # 無音判定の閾値（音量レベル）
        self.min_silence_duration = 2.0          # 沈黙と判定する最小時間（秒）
        self.audio_buffer = deque(maxlen=100)    # 音声履歴バッファ（最大100フレーム）
        self.is_speaking = False                 # 現在話しているかどうか
        self.current_silence_duration = 0        # 現在の沈黙継続時間
        
        # 分析用パラメータ
        self.silence_patterns = []               # 沈黙パターンの履歴
        self.speech_segments = []                # 発話セグメントの履歴
        self.context_window = 5                  # コンテキスト分析の窓サイズ（秒）

    def process_audio(self, audio_data):
        """
        音声データを処理し、沈黙の状態を分析
        
        Parameters:
        - audio_data: バイト列またはnumpy配列の音声データ
        
        Returns:
        - dict: 沈黙分析の結果
        """
        current_time = time.time()
        
        # 音声データをnumpy配列に変換し、RMSレベルを計算
        audio_array = np.frombuffer(audio_data, dtype=np.float32)
        rms = self._calculate_rms(audio_array)
        
        # 音声バッファに現在のフレームを追加
        self.audio_buffer.append({
            'rms': rms,
            'timestamp': current_time,
            'duration': len(audio_array) / 16000  # サンプリングレート16kHzを仮定
        })
        
        # 音声/沈黙の状態を更新
        self._update_speech_state(rms, current_time)
        
        # 分析結果を返す
        return self._create_analysis_result()

    def _calculate_rms(self, audio_array):
        """
        音声データのRMS（二乗平均平方根）レベルを計算
        
        Parameters:
        - audio_array: numpy配列の音声データ
        
        Returns:
        - float: RMSレベル
        """
        return np.sqrt(np.mean(np.square(audio_array)))

    def _update_speech_state(self, rms, current_time):
        """
        音声/沈黙の状態を更新
        
        Parameters:
        - rms: 現在のRMSレベル
        - current_time: 現在の時刻
        """
        if rms > self.silence_threshold:
            if not self.is_speaking:
                # 発話開始を検出
                self.is_speaking = True
                self._handle_speech_start(current_time)
            self.last_speech_time = current_time
            self.current_silence_duration = 0
        else:
            # 沈黙時間の更新
            self.current_silence_duration = current_time - self.last_speech_time
            if self.current_silence_duration >= self.min_silence_duration:
                if self.is_speaking:
                    # 沈黙開始を検出
                    self.is_speaking = False
                    self._handle_silence_start(current_time)

    def _handle_speech_start(self, time):
        """
        発話開始時の処理
        
        Parameters:
        - time: 発話開始時刻
        """
        if self.current_silence_duration >= self.min_silence_duration:
            # 有意な沈黙の後の発話開始
            self.silence_patterns.append({
                'duration': self.current_silence_duration,
                'start_time': self.last_speech_time,
                'end_time': time
            })

    def _handle_silence_start(self, time):
        """
        沈黙開始時の処理
        
        Parameters:
        - time: 沈黙開始時刻
        """
        self.speech_segments.append({
            'duration': time - self.last_speech_time,
            'start_time': self.last_speech_time,
            'end_time': time
        })

    def _create_analysis_result(self):
        """
        分析結果を生成
        
        Returns:
        - dict: 詳細な分析結果
        """
        return {
            'is_silent': not self.is_speaking,
            'silence_duration': self.current_silence_duration,
            'speech_state': {
                'is_speaking': self.is_speaking,
                'last_speech_time': self.last_speech_time
            },
            'audio_metrics': self._calculate_audio_metrics(),
            'silence_pattern': self._analyze_silence_pattern()
        }

    def _calculate_audio_metrics(self):
        """
        音声メトリクスの計算
        
        Returns:
        - dict: 音声の統計的指標
        """
        recent_frames = list(self.audio_buffer)
        if not recent_frames:
            return {}

        rms_values = [frame['rms'] for frame in recent_frames]
        return {
            'average_rms': np.mean(rms_values),
            'max_rms': np.max(rms_values),
            'min_rms': np.min(rms_values),
            'rms_variance': np.var(rms_values)
        }

    def _analyze_silence_pattern(self):
        """
        沈黙パターンの分析
        
        Returns:
        - dict: 沈黙パターンの特徴
        """
        if not self.silence_patterns:
            return {}

        recent_patterns = [
            p for p in self.silence_patterns 
            if time.time() - p['end_time'] <= self.context_window
        ]

        return {
            'pattern_count': len(recent_patterns),
            'average_duration': np.mean([p['duration'] for p in recent_patterns]),
            'pattern_frequency': len(recent_patterns) / self.context_window,
            'max_duration': max([p['duration'] for p in recent_patterns], default=0)
        }

    def get_silence_statistics(self):
        """
        沈黙の統計情報を取得
        
        Returns:
        - dict: 詳細な統計情報
        """
        if not self.silence_patterns:
            return {}

        durations = [p['duration'] for p in self.silence_patterns]
        return {
            'total_silences': len(durations),
            'average_duration': np.mean(durations),
            'max_duration': np.max(durations),
            'min_duration': np.min(durations),
            'duration_std': np.std(durations),
            'total_silence_time': sum(durations),
            'silence_frequency': len(durations) / (time.time() - self.silence_patterns[0]['start_time'])
        }

    def reset_statistics(self):
        """統計情報のリセット"""
        self.silence_patterns = []
        self.speech_segments = []
        self.audio_buffer.clear()
        self.is_speaking = False
        self.current_silence_duration = 0
        self.last_speech_time = time.time()
