"""音声と正解の文から、音素・単語・文の発音スコアと誤りの指摘を作る"""
import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from . import acoustic, scoring
from .alignment import AlignedUnit, batched_ctc_log_likelihood, forced_align, unit_emissions
from .feedback import describe_issue
from .phonemes import (ACCEPTABLE, L2_TOKENS, VOWELS, Unit, WordSpec, acceptable_tokens,
                       build_units, display_phone, words_from_text)

logger = logging.getLogger(__name__)

MISSING_EVIDENCE = 0.15        # 区間内の発音の痕跡がこれ未満なら「発音されていない」

# 「明確な置き換え」: モデルが別の音だとほぼ確信していて、置き換えた列の方がはるかにもっともらしい。
# speechocean762 の採点者はこうした音素も寛容に採点することが多い（満点でないのは約半数）が、
# r → l のような置き換えは日本語話者にとって最も直す価値が高いので、学習した判定に加えて指摘する。
CLEAR_SUB_MAX_TARGET = 0.02
CLEAR_SUB_MIN_COMPETITOR = 0.8
CLEAR_SUB_MAX_AF = -5.0
LONG_PAUSE_SECONDS = 0.5
MAX_ISSUES = 8
AF_WINDOW_MARGIN = 3           # アライメントフリー GOP で単語の前後に足すフレーム数


@dataclass
class _Word:
    spec: WordSpec
    pronunciation: Optional[List[str]]
    units: List[Unit]


def _build_word(spec: WordSpec, index: int, pronunciation: Optional[List[str]]) -> _Word:
    if pronunciation is None:
        return _Word(spec, None, [Unit(phones=[], word_index=index, wildcard=True)])
    return _Word(spec, pronunciation, build_units(pronunciation, index))


class PronunciationAssessor:
    def __init__(self, model: Optional[acoustic.AcousticModel] = None):
        self.model = model or acoustic.load_model()
        vocab = self.model.vocab
        self.blank_id = self.model.blank_id
        self.all_token_ids = [i for i in range(len(vocab)) if i != self.blank_id and not vocab[i].startswith('<')]
        self.vowel_ids = self.model.token_ids(scoring.VOWEL_TOKENS)
        # 置き換え候補: 英語の各音素と、学習者の誤りとして現れやすい音
        alternatives = [(base, acceptable_tokens(base + '1' if base in VOWELS else base)) for base in ACCEPTABLE]
        alternatives += [(f'~{token}', frozenset({token})) for token in sorted(L2_TOKENS)]
        self.alternatives = alternatives

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------
    def assess_file(self, audio_path: str, text: str) -> dict:
        audio = acoustic.load_audio(audio_path)
        return self.assess(acoustic.frame_posteriors(audio, self.model), words_from_text(text))

    def assess(self, posteriors: np.ndarray, word_specs: Sequence[WordSpec]) -> dict:
        word_specs = list(word_specs)
        if not word_specs:
            raise ValueError('There is no text to compare with.')

        words = [_build_word(spec, i, spec.pronunciations[0] if spec.in_lexicon else None)
                 for i, spec in enumerate(word_specs)]
        aligned = self._align(posteriors, words)
        words = self._choose_pronunciations(posteriors, words, aligned)
        if any(len(spec.pronunciations) > 1 for spec in word_specs):
            aligned = self._align(posteriors, words)
        return self._score(posteriors, words, aligned)

    # ------------------------------------------------------------------
    # アライメント
    # ------------------------------------------------------------------
    def _token_ids(self, unit: Unit) -> List[int]:
        return self.all_token_ids if unit.wildcard else self.model.token_ids(unit.acceptable)

    def _align_units(self, posteriors, units: Sequence[Unit], return_score=False):
        emissions = unit_emissions(posteriors, [self._token_ids(u) for u in units])
        blank = np.log(posteriors[:, self.blank_id] + 1e-12)
        return forced_align(emissions, blank, [u.label for u in units], return_score=return_score)

    def _align(self, posteriors, words: Sequence[_Word]) -> List[AlignedUnit]:
        units = [u for w in words for u in w.units]
        return self._align_units(posteriors, units)

    def _word_spans(self, words, aligned):
        spans, index = [], 0
        for w in words:
            first, last = aligned[index], aligned[index + len(w.units) - 1]
            spans.append((first.start, last.end))
            index += len(w.units)
        return spans

    def _choose_pronunciations(self, posteriors, words, aligned) -> List[_Word]:
        """辞書に複数の発音がある単語（the: ðə / ðiː など）は、音声に最も合う発音を選ぶ"""
        spans = self._word_spans(words, aligned)
        chosen = []
        for i, (word, (start, end)) in enumerate(zip(words, spans)):
            if len(word.spec.pronunciations) <= 1:
                chosen.append(word)
                continue
            best, best_score = word, None
            for pronunciation in word.spec.pronunciations:
                candidate = _build_word(word.spec, i, pronunciation)
                try:
                    _, score = self._align_units(posteriors[start:end], candidate.units, return_score=True)
                except ValueError:
                    continue
                if best_score is None or score > best_score:
                    best, best_score = candidate, score
            chosen.append(best)
        return chosen

    # ------------------------------------------------------------------
    # 採点
    # ------------------------------------------------------------------
    def _alignment_free(self, posteriors, words, aligned) -> dict:
        """単語ごとに、各単位を別の音に置き換えた列・抜かした列と正解の列の対数尤度を比べる。

        区間の切り方に左右されない GOP（CTC ベースのアライメントフリー GOP）。
        戻り値: {単位の通し番号: (af_sub, af_del)}
        """
        blank_all = np.log(posteriors[:, self.blank_id] + 1e-12)
        spans = self._word_spans(words, aligned)
        T = posteriors.shape[0]
        features = {}
        offset = 0
        for word, (start, end) in zip(words, spans):
            units = word.units
            n = len(units)
            first_index = offset
            offset += n
            if any(u.wildcard for u in units):
                continue
            lo, hi = max(0, start - AF_WINDOW_MARGIN), min(T, end + AF_WINDOW_MARGIN)
            window = posteriors[lo:hi]
            blank = blank_all[lo:hi]
            W = hi - lo

            def column(ids):
                return np.log(window[:, ids].sum(axis=1) + 1e-12) if ids else np.full(W, np.log(1e-12))

            canon_ids = [self._token_ids(u) for u in units]
            canon = np.stack([column(ids) for ids in canon_ids], axis=1)  # (W, n)
            labels = [u.label for u in units]

            def same_prev(seq):
                return np.array([i > 0 and seq[i] == seq[i - 1] for i in range(len(seq))])

            canon_ll = batched_ctc_log_likelihood(canon[None], blank, same_prev(labels)[None])[0]

            # 置き換え
            sub_emissions, sub_same, owners = [], [], []
            for k, unit in enumerate(units):
                for label, tokens in self.alternatives:
                    ids = self.model.token_ids(tokens - unit.acceptable)
                    if not ids or label == unit.label:
                        continue
                    emissions = canon.copy()
                    emissions[:, k] = column(ids)
                    seq = labels[:k] + [label] + labels[k + 1:]
                    sub_emissions.append(emissions)
                    sub_same.append(same_prev(seq))
                    owners.append(k)
            best_sub = np.full(n, -np.inf)
            if sub_emissions:
                lls = batched_ctc_log_likelihood(np.stack(sub_emissions), blank, np.stack(sub_same))
                for k, ll in zip(owners, lls):
                    best_sub[k] = max(best_sub[k], ll)

            # 抜かした場合
            if n > 1:
                del_emissions = np.stack([np.delete(canon, k, axis=1) for k in range(n)])
                del_same = np.stack([same_prev(labels[:k] + labels[k + 1:]) for k in range(n)])
                del_ll = batched_ctc_log_likelihood(del_emissions, blank, del_same)
            else:
                del_ll = np.array([float(blank.sum())])

            for k in range(n):
                features[first_index + k] = (float(canon_ll - best_sub[k]), float(canon_ll - del_ll[k]))
        return features

    def phone_features(self, posteriors, words, aligned):
        """各音素の特徴量を返す（評価・係数の学習にも使う）。

        戻り値: [(word_index, PhoneSpec, PhoneFeatures, inserted_vowel or None), ...]
        """
        units = [u for w in words for u in w.units]
        alignment_free = self._alignment_free(posteriors, words, aligned)
        results = []
        for k, (unit, span) in enumerate(zip(units, aligned)):
            if unit.wildcard:
                continue
            frames = np.arange(span.start, max(span.end, span.start + 1))

            inserted = None
            last_phone = unit.phones[-1]
            next_unit = units[k + 1] if k + 1 < len(units) else None
            word_final = next_unit is None or next_unit.word_index != unit.word_index
            next_is_consonant = (next_unit is not None and not next_unit.wildcard
                                 and not next_unit.phones[0].is_vowel)
            if not last_phone.is_vowel and (word_final or next_is_consonant):
                trailing = frames[frames > span.last_emission]
                inserted = scoring.find_inserted_vowel(
                    posteriors, trailing, self.blank_id, self.vowel_ids, self.model.vocab)
                if inserted:
                    frames = np.setdiff1d(frames, inserted['frames'])

            for phone in unit.phones:
                features = scoring.phone_features(
                    posteriors, frames, self.blank_id,
                    self.model.token_ids(phone.acceptable), self.model.vocab)
                features.af_sub, features.af_del = alignment_free.get(k, (0.0, 0.0))
                results.append((unit.word_index, phone, features,
                                inserted if phone is last_phone else None))
        return results

    @staticmethod
    def _is_clear_substitution(phone, features, merged: bool) -> bool:
        if features.target >= CLEAR_SUB_MAX_TARGET or features.competitor <= CLEAR_SUB_MIN_COMPETITOR:
            return False
        if features.heard in phone.acceptable:
            return False
        # 「母音 + r」のようにまとめた単位では置き換えの尤度比が音素ごとに分けられないので、
        # 区間内の確率の偏りだけで判断する（car を「カー」と r なしで言った場合など）
        return merged or features.af_sub < CLEAR_SUB_MAX_AF

    def _score(self, posteriors, words, aligned) -> dict:
        frame = acoustic.FRAME_SECONDS
        phone_rows = self.phone_features(posteriors, words, aligned)
        merged_phones = {id(p) for w in words for u in w.units if len(u.phones) > 1 for p in u.phones}

        word_phones = {i: [] for i in range(len(words))}
        for word_index, phone, features, inserted in phone_rows:
            probability = scoring.phone_probability(features, inserted_vowel=bool(inserted))
            quality = scoring.phone_quality(features, inserted_vowel=bool(inserted))
            issue = None
            if inserted:
                # 子音のあとの余分な母音は、日本語話者に多く直す価値が高いので常に指摘する
                issue = 'inserted_vowel'
            elif quality < scoring.DETECTION_THRESHOLD or self._is_clear_substitution(
                    phone, features, merged=id(phone) in merged_phones):
                if features.evidence < MISSING_EVIDENCE:
                    issue = 'missing'
                elif features.heard and features.heard not in phone.acceptable:
                    issue = 'substitution'
                else:
                    issue = 'unclear'

            heard = inserted['token'] if inserted else features.heard
            expected = display_phone(phone.phone)
            word_phones[word_index].append({
                'phone': phone.phone,
                'ipa': expected,
                'score': round(quality * 100),
                'grade': scoring.phone_grade(quality, issue is not None),
                'heard': heard if issue else None,
                'issue': issue,
                'message': describe_issue(issue, expected, heard, phone.base) if issue else None,
                '_probability': probability,
            })

        spans = self._word_spans(words, aligned)
        unit_index = 0
        word_results = []
        for i, word in enumerate(words):
            units = aligned[unit_index:unit_index + len(word.units)]
            unit_index += len(word.units)
            phones = word_phones[i]
            probabilities = [p.pop('_probability') for p in phones]
            score = scoring.word_score(probabilities) if phones else None
            word_results.append({
                'text': word.spec.text,
                'scored': bool(phones),
                'score': round(score * 100) if phones else None,
                'grade': scoring.word_grade(score, [p['grade'] for p in phones]),
                'start': round(units[0].start * frame, 2),
                'end': round(min(units[-1].last_emission + 1, spans[i][1]) * frame + 0.1, 2),
                'phones': phones,
                '_probability': scoring.word_score(probabilities) if phones else None,
                '_weight': len(phones),
            })

        scored = [w for w in word_results if w['scored']]
        sentence = scoring.sentence_score(
            [w['_probability'] for w in scored], [w['_weight'] for w in scored]) if scored else 0.0
        for w in word_results:
            w.pop('_probability')
            w.pop('_weight')

        issues = sorted(
            ({'word': w['text'], 'start': w['start'], 'end': w['end'], **p}
             for w in word_results for p in w['phones'] if p['issue']),
            key=lambda p: p['score'],
        )[:MAX_ISSUES]

        return {
            'score': round(sentence * 100),
            'grade': scoring.word_grade(sentence if scored else None, []),
            'words': word_results,
            'issues': issues,
            'fluency': self._fluency(words, aligned, posteriors.shape[0]),
            'scored_words': len(scored),
            'unscored_words': [w['text'] for w in word_results if not w['scored']],
        }

    def _fluency(self, words, aligned, total_frames) -> dict:
        frame = acoustic.FRAME_SECONDS
        spans, index = [], 0
        for w in words:
            units = aligned[index:index + len(w.units)]
            index += len(w.units)
            spans.append((units[0].first_emission, units[-1].last_emission))

        pauses = [
            (nxt[0] - prev[1]) * frame
            for prev, nxt in zip(spans, spans[1:])
            if (nxt[0] - prev[1]) * frame >= LONG_PAUSE_SECONDS
        ]
        speaking_seconds = max((spans[-1][1] - spans[0][0]) * frame, frame)
        return {
            'words_per_minute': round(len(words) / speaking_seconds * 60),
            'speaking_seconds': round(speaking_seconds, 1),
            'long_pauses': len(pauses),
            'long_pause_seconds': round(sum(pauses), 1),
        }


_assessor_lock = __import__('threading').Lock()
_assessor = None


def get_assessor() -> PronunciationAssessor:
    """モデルを読み込んだ評価器をプロセス内で使い回す"""
    global _assessor
    with _assessor_lock:
        if _assessor is None:
            _assessor = PronunciationAssessor()
        return _assessor
