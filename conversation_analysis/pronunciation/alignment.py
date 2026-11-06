"""CTC の強制アライメント（Viterbi）。

正解の単位列（音素）を、音声のどのフレームに対応させると確率が最大になるかを求める。
各単位の放出確率は「その単位として正しいとみなす記号の確率の和」を使う。
"""
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

NEG_INF = -1e30
EPS = 1e-12


@dataclass
class AlignedUnit:
    start: int   # この単位が最初に現れるフレーム
    end: int     # 次の単位が始まるフレーム（排他的）。間の無音・ブランクもこの単位に含む
    first_emission: int
    last_emission: int


def unit_emissions(posteriors: np.ndarray, token_sets: Sequence[List[int]]) -> np.ndarray:
    """(T, U) の対数放出確率。token_sets[u] は単位 u として受け入れる記号 id のリスト"""
    T = posteriors.shape[0]
    emissions = np.empty((T, len(token_sets)))
    for u, ids in enumerate(token_sets):
        emissions[:, u] = np.log(posteriors[:, ids].sum(axis=1) + EPS) if ids else np.log(EPS)
    return emissions


def forced_align(emissions: np.ndarray, blank_logprob: np.ndarray, labels: Sequence,
                 return_score: bool = False):
    """CTC の Viterbi アライメント。

    emissions: (T, U) 各単位の対数放出確率
    blank_logprob: (T,) ブランクの対数確率
    labels: 長さ U。同じラベルが連続する場合はブランクを挟む必要がある（CTC の規則）
    """
    T, U = emissions.shape
    if U == 0:
        return ([], 0.0) if return_score else []
    S = 2 * U + 1
    repeats = sum(1 for i in range(1, U) if labels[i] == labels[i - 1])
    if T < U + repeats:
        raise ValueError('The audio is too short for the expected text.')

    # 状態 s: 偶数 = ブランク、奇数 = 単位 (s-1)//2
    state_unit = np.full(S, -1)
    state_unit[1::2] = np.arange(U)
    can_skip = np.zeros(S, dtype=bool)  # s-2 から直接来られるか（異なる単位の間でブランクを省略）
    for s in range(3, S, 2):
        u = state_unit[s]
        can_skip[s] = labels[u] != labels[u - 1]

    def emit(t):
        e = np.empty(S)
        e[0::2] = blank_logprob[t]
        e[1::2] = emissions[t]
        return e

    score = np.full(S, NEG_INF)
    score[0] = blank_logprob[0]
    score[1] = emissions[0, 0]
    backpointer = np.zeros((T, S), dtype=np.int8)  # 0: 同じ状態, 1: s-1, 2: s-2

    for t in range(1, T):
        stay = score
        prev1 = np.concatenate(([NEG_INF], score[:-1]))
        prev2 = np.concatenate(([NEG_INF, NEG_INF], score[:-2]))
        prev2 = np.where(can_skip, prev2, NEG_INF)
        candidates = np.vstack([stay, prev1, prev2])
        choice = candidates.argmax(axis=0)
        score = candidates[choice, np.arange(S)] + emit(t)
        backpointer[t] = choice

    # 終端は最後のブランクか最後の単位
    s = S - 1 if score[S - 1] >= score[S - 2] else S - 2
    best_score = float(score[s])
    path = np.empty(T, dtype=np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= backpointer[t, s]

    frame_units = np.where(path % 2 == 1, (path - 1) // 2, -1)
    firsts = np.full(U, -1)
    lasts = np.full(U, -1)
    for t, u in enumerate(frame_units):
        if u >= 0:
            if firsts[u] < 0:
                firsts[u] = t
            lasts[u] = t

    aligned = []
    for u in range(U):
        start = firsts[u]
        end = firsts[u + 1] if u + 1 < U else T
        aligned.append(AlignedUnit(start=int(start), end=int(end),
                                   first_emission=int(firsts[u]), last_emission=int(lasts[u])))
    return (aligned, best_score) if return_score else aligned


def batched_ctc_log_likelihood(emissions: np.ndarray, blank_logprob: np.ndarray,
                               same_as_previous: np.ndarray) -> np.ndarray:
    """複数のラベル列について、CTC の対数尤度 log P(ラベル列 | 音声) をまとめて計算する。

    emissions: (B, T, L) 各ラベル列の各位置の対数放出確率（B 本の列、長さはすべて L）
    blank_logprob: (T,) ブランクの対数確率
    same_as_previous: (B, L) 位置 i のラベルが位置 i-1 と同じか（同じならブランクを挟む必要がある）
    戻り値: (B,)
    """
    B, T, L = emissions.shape
    if L == 0:
        return np.full(B, float(blank_logprob.sum()))
    if T == 0:
        return np.full(B, NEG_INF)
    S = 2 * L + 1
    can_skip = np.zeros((B, S), dtype=bool)
    can_skip[:, 3::2] = ~same_as_previous[:, 1:]

    alpha = np.full((B, S), NEG_INF)
    alpha[:, 0] = blank_logprob[0]
    alpha[:, 1] = emissions[:, 0, 0]
    pad1 = np.full((B, 1), NEG_INF)
    pad2 = np.full((B, 2), NEG_INF)
    for t in range(1, T):
        prev1 = np.concatenate((pad1, alpha[:, :-1]), axis=1)
        prev2 = np.where(can_skip, np.concatenate((pad2, alpha[:, :-2]), axis=1), NEG_INF)
        combined = np.logaddexp(np.logaddexp(alpha, prev1), prev2)
        emit = np.empty((B, S))
        emit[:, 0::2] = blank_logprob[t]
        emit[:, 1::2] = emissions[:, t, :]
        alpha = combined + emit
    return np.logaddexp(alpha[:, -1], alpha[:, -2])
