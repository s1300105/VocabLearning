"""音素ごとの GOP（Goodness of Pronunciation）特徴量と、点数への換算。

換算の係数は、専門家が音素・単語・文ごとに採点した公開データセット speechocean762 で
学習したもの（`python manage.py evaluate_pronunciation --fit` で再計算できる）。
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
from django.core.exceptions import ImproperlyConfigured


EPS = 1e-6

# 子音のあとに余分な母音が入る誤り（street → sutoriito）の検出に使う、母音とみなす記号
VOWEL_TOKENS = frozenset({
    'a', 'aː', 'ɑ', 'ɑː', 'ɐ', 'æ', 'ʌ', 'ə', 'e', 'eː', 'ɛ', 'i', 'iː', 'ɪ', 'ᵻ', 'o', 'oː', 'ɔ', 'ɔː',
    'u', 'uː', 'ʊ', 'ɯ', 'ɨ', 'ɚ', 'ɜ', 'ɜː', 'ɒ',
})
INSERTION_THRESHOLD = 0.3


# ---------------------------------------------------------------------------
# 係数（calibration.json。`evaluate_pronunciation --fit --save` で再計算できる）
# ---------------------------------------------------------------------------
CALIBRATION_PATH = Path(__file__).with_name('calibration.json')
LOW_WORD_THRESHOLD = 0.6
AF_CLIP = 15.0

# 音素の特徴量。どの音素にも共通の「正しい音らしさ」の指標だけを使う。
# （区間内でどの音に確率が流れたかの分布も試したが、学習データ（中国語話者）にほとんど
#   現れない音 ── 日本語話者に多い ɸ や ɯ など ── の係数が不安定になり、汎化しないため使わない）
FEATURE_NAMES = ['bias', 'log_target', 'gop', 'log_peak', 'log_evidence', 'inserted_vowel', 'af_sub', 'af_del']


def _load_calibration():
    with open(CALIBRATION_PATH, encoding='utf-8') as f:
        calibration = json.load(f)
    if calibration['phone']['features'] != FEATURE_NAMES:
        raise ImproperlyConfigured('calibration.json does not match the current features. '
                                   'Run `manage.py evaluate_pronunciation --fit --save`.')
    return (np.array(calibration['phone']['weights']), np.array(calibration['phone_detection']['weights']),
            float(calibration['phone_detection'].get('threshold', 0.5)),
            np.array(calibration['word']['weights']), np.array(calibration['sentence']['weights']))


# 点数用と誤り検出用で、音素のモデルを分けている。
# 学習データでは「誤り」とされた音素が約5%しかないため、人間の点数に合わせたモデル（点数用）は
# 予測がほぼ 0.9 以上に固まり、はっきりした誤りでも見分けにくい。検出用は「誤り」の重みを
# DETECTION_BALANCE 倍にして学習し、DETECTION_THRESHOLD 未満を「要練習」と判定する。
# しきい値は学習データで「指摘の半分以上が実際の誤り」を保ちつつ最も多く誤りを拾える値。
# 音素（点数用）: sigmoid(PHONE_WEIGHTS · features)
# 音素（検出用）: sigmoid(DETECTION_WEIGHTS · features)
# 単語: clip(WORD_WEIGHTS · [1, mean_phone, min_phone])（点数用の音素の値から）
# 文:   clip(SENTENCE_WEIGHTS · [1, mean_word, share_of_low_words])
DETECTION_BALANCE = 3.0
DETECTION_MIN_PRECISION = 0.5
PHONE_WEIGHTS, DETECTION_WEIGHTS, DETECTION_THRESHOLD, WORD_WEIGHTS, SENTENCE_WEIGHTS = _load_calibration()

WORD_GOOD = 0.8   # 単語の点数（人間の採点の尺度）の色分け
WORD_FAIR = 0.6


def phone_grade(quality: float, has_issue: bool) -> str:
    if has_issue or quality < DETECTION_THRESHOLD:
        return 'poor'
    if quality < (DETECTION_THRESHOLD + 1.0) / 2:
        return 'fair'
    return 'good'


def word_grade(score: Optional[float], phone_grades: Sequence[str]) -> str:
    """単語の色分け。点数が高くても「要練習」の音を含む単語は good にしない"""
    if score is None:
        return 'unscored'
    if score < WORD_FAIR:
        return 'poor'
    if score < WORD_GOOD or 'poor' in phone_grades:
        return 'fair'
    return 'good'


@dataclass
class PhoneFeatures:
    target: float          # 区間内で「正しい記号」が占める確率
    competitor: float      # 正しくない記号のうち最大のもの
    heard: Optional[str]   # 最も確率が高かった記号
    peak: float            # 区間内での「正しい記号」の最大フレーム確率
    evidence: float        # 区間内のブランク以外の確率の合計（ほぼ0なら発音されていない）
    # アライメントに依存しない GOP: 単語の範囲で「正解の列」と「この音素を置き換えた / 抜かした列」の
    # 対数尤度の差。正なら正解の方がもっともらしい
    af_sub: float = 0.0
    af_del: float = 0.0

    @property
    def gop(self) -> float:
        return float(np.log(self.target + EPS) - np.log(max(self.target, self.competitor) + EPS))

    def vector(self, inserted_vowel: bool = False) -> np.ndarray:
        return np.array([
            1.0,
            np.log(self.target + EPS),
            self.gop,
            np.log(self.peak + EPS),
            np.log(min(self.evidence, 3.0) + EPS),
            1.0 if inserted_vowel else 0.0,
            float(np.clip(self.af_sub, -AF_CLIP, AF_CLIP)),
            float(np.clip(self.af_del, -AF_CLIP, AF_CLIP)),
        ])


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def phone_probability(features: PhoneFeatures, inserted_vowel: bool = False) -> float:
    """人間が付ける点数（0〜1）の推定。単語・文の点数の計算に使う"""
    return float(sigmoid(PHONE_WEIGHTS @ features.vector(inserted_vowel)))


def phone_quality(features: PhoneFeatures, inserted_vowel: bool = False) -> float:
    """誤りを見分けるための値（0〜1）。0.5 未満を「要練習」とし、音素の表示にも使う"""
    return float(sigmoid(DETECTION_WEIGHTS @ features.vector(inserted_vowel)))


def word_vector(phone_scores: Sequence[float]) -> np.ndarray:
    return np.array([1.0, float(np.mean(phone_scores)), float(np.min(phone_scores))])


def word_score(phone_scores: Sequence[float]) -> float:
    return float(np.clip(WORD_WEIGHTS @ word_vector(phone_scores), 0.0, 1.0))


def sentence_vector(word_scores: Sequence[float], weights: Sequence[float]) -> np.ndarray:
    word_scores = np.asarray(word_scores, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mean = float(np.average(word_scores, weights=weights))
    low_share = float(np.average(word_scores < LOW_WORD_THRESHOLD, weights=weights))
    return np.array([1.0, mean, low_share])


def sentence_score(word_scores: Sequence[float], weights: Sequence[float]) -> float:
    if len(word_scores) == 0:
        return 0.0
    return float(np.clip(SENTENCE_WEIGHTS @ sentence_vector(word_scores, weights), 0.0, 1.0))


def segment_distribution(posteriors: np.ndarray, frames: np.ndarray, blank_id: int) -> Dict[int, float]:
    """区間内のブランク以外の記号の確率分布（ブランクの確率で正規化）"""
    probs = posteriors[frames]
    nonblank = probs.copy()
    nonblank[:, blank_id] = 0.0
    total = nonblank.sum()
    if total <= 0:
        return {}
    summed = nonblank.sum(axis=0) / total
    return {int(i): float(summed[i]) for i in np.nonzero(summed > 1e-4)[0]}


def phone_features(posteriors: np.ndarray, frames: np.ndarray, blank_id: int,
                   acceptable_ids: Sequence[int], vocab: Sequence[str]) -> PhoneFeatures:
    acceptable_ids = list(acceptable_ids)
    distribution = segment_distribution(posteriors, frames, blank_id)
    target = sum(distribution.get(i, 0.0) for i in acceptable_ids)
    others = {i: p for i, p in distribution.items() if i not in set(acceptable_ids)}
    competitor = max(others.values()) if others else 0.0
    heard_id = max(distribution, key=distribution.get) if distribution else None
    peak = float(posteriors[np.ix_(frames, acceptable_ids)].sum(axis=1).max()) if acceptable_ids and len(frames) else 0.0
    evidence = float((1.0 - posteriors[frames, blank_id]).sum()) if len(frames) else 0.0
    return PhoneFeatures(
        target=float(target),
        competitor=float(competitor),
        heard=vocab[heard_id] if heard_id is not None else None,
        peak=peak,
        evidence=evidence,
    )


def find_inserted_vowel(posteriors: np.ndarray, frames: np.ndarray, blank_id: int,
                        vowel_ids: Sequence[int], vocab: Sequence[str]) -> Optional[dict]:
    """子音のあとに母音が入っていないか（例: street を「ストリート」と発音）を調べる。

    見つかった場合は {'token': 記号, 'frames': 該当フレーム} を返す。
    """
    if len(frames) == 0 or not vowel_ids:
        return None
    vowel_probs = posteriors[np.ix_(frames, list(vowel_ids))]
    best = vowel_probs.max(axis=1)
    hits = np.nonzero(best > INSERTION_THRESHOLD)[0]
    if len(hits) == 0:
        return None
    best_index = hits[np.argmax(best[hits])]
    token_id = list(vowel_ids)[int(vowel_probs[best_index].argmax())]
    return {'token': vocab[token_id], 'frames': frames[hits]}
