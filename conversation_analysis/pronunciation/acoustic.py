"""音素認識モデル（wav2vec2）で、音声の各フレームが各記号である確率を求める。

モデルは Hugging Face から一度だけダウンロードし、以降はローカルで実行する（外部 API は使わない）。
"""
import json
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import List

import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SECONDS = 0.02           # wav2vec2 は 20ms ごとに1フレームを出力する
CHUNK_SECONDS = 20.0           # 長い音声はメモリ節約のため区切って推論する
CONTEXT_SECONDS = 1.0          # 区切りの前後に足す文脈（境界での認識の乱れを防ぐ）

_inference_lock = threading.Lock()


@dataclass
class AcousticModel:
    model: object
    feature_extractor: object
    vocab: List[str]           # id -> 記号
    blank_id: int
    allowed_mask: np.ndarray   # 採点に使う記号（ブランクを含む）

    def token_ids(self, tokens) -> List[int]:
        index = {t: i for i, t in enumerate(self.vocab)}
        return sorted(index[t] for t in tokens if t in index)


@lru_cache(maxsize=1)
def load_model() -> AcousticModel:
    """モデルの読み込みは重い（初回は約1.3GBのダウンロード）ので、プロセス内で一度だけ行う"""
    import torch
    from huggingface_hub import hf_hub_download
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

    model_id = settings.PRONUNCIATION_MODEL
    logger.info(f"Loading pronunciation model {model_id}")
    model = Wav2Vec2ForCTC.from_pretrained(model_id)
    model.eval()
    feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_id)

    with open(hf_hub_download(model_id, 'vocab.json'), encoding='utf-8') as f:
        token_to_id = json.load(f)
    vocab = [''] * len(token_to_id)
    for token, idx in token_to_id.items():
        vocab[idx] = token

    from .phonemes import model_inventory

    blank_id = model.config.pad_token_id
    inventory = model_inventory()
    allowed_mask = np.array([token in inventory for token in vocab])
    allowed_mask[blank_id] = True
    missing = inventory - set(vocab)
    if missing:
        logger.warning(f"Tokens not in the model vocabulary: {sorted(missing)}")

    torch.set_grad_enabled(False)
    return AcousticModel(model=model, feature_extractor=feature_extractor, vocab=vocab,
                         blank_id=blank_id, allowed_mask=allowed_mask)


def load_audio(path: str) -> np.ndarray:
    import librosa

    audio, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    return audio.astype(np.float32)


def frame_logits(audio: np.ndarray, acoustic: AcousticModel = None) -> np.ndarray:
    """(フレーム数, 記号数) のロジット（softmax 前の値）を返す"""
    acoustic = acoustic or load_model()
    chunk = int(CHUNK_SECONDS * SAMPLE_RATE)
    context = int(CONTEXT_SECONDS * SAMPLE_RATE)
    samples_per_frame = int(FRAME_SECONDS * SAMPLE_RATE)

    pieces = []
    with _inference_lock:
        for start in range(0, max(len(audio), 1), chunk):
            end = min(start + chunk, len(audio))
            left = max(0, start - context)
            right = min(len(audio), end + context)
            inputs = acoustic.feature_extractor(
                audio[left:right], sampling_rate=SAMPLE_RATE, return_tensors='pt')
            logits = acoustic.model(inputs.input_values).logits[0].numpy()

            # 文脈部分を除いた、このチャンク本体のフレームだけを使う
            first = (start - left) // samples_per_frame
            count = int(np.ceil((end - start) / samples_per_frame))
            pieces.append(logits[first:first + count])

    return np.concatenate(pieces, axis=0) if pieces else np.zeros((0, len(acoustic.vocab)))


def posteriors_from_logits(logits: np.ndarray, acoustic: AcousticModel = None) -> np.ndarray:
    """採点に使う記号だけで softmax を取り、(フレーム数, 記号数) の確率行列を返す"""
    acoustic = acoustic or load_model()
    masked = np.where(acoustic.allowed_mask, logits.astype(np.float64), -np.inf)
    masked -= masked.max(axis=1, keepdims=True)
    probs = np.exp(masked)
    return probs / probs.sum(axis=1, keepdims=True)


def frame_posteriors(audio: np.ndarray, acoustic: AcousticModel = None) -> np.ndarray:
    acoustic = acoustic or load_model()
    return posteriors_from_logits(frame_logits(audio, acoustic), acoustic)
