"""発音評価の精度を、専門家が採点した公開データセット speechocean762 で測る。

    python manage.py evaluate_pronunciation --data-dir path/to/speechocean762
    python manage.py evaluate_pronunciation --data-dir ... --fit    # 換算係数を学習し直す

data-dir には https://huggingface.co/datasets/mispeech/speechocean762 の
data/train-*.parquet と data/test-*.parquet を train.parquet / test.parquet として置く。
音素・単語・文それぞれについて、人間の点数とのピアソン相関係数（PCC）を表示する。
"""
import io
import os
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from conversation_analysis.pronunciation import acoustic, scoring
from conversation_analysis.pronunciation.assessor import PronunciationAssessor, _build_word
from conversation_analysis.pronunciation.phonemes import WordSpec


def pcc(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.corrcoef(a, b)[0, 1]) if len(a) > 1 else float('nan')


def fit_logistic(X, y, l2=1.0, iterations=100, balance=1.0):
    """確率（0〜1 の連続値）を目的変数にしたロジスティック回帰（ニュートン法）。

    X の 0 列目はバイアス（常に 1）。ほかの列は標準化して L2 正則化をかけ、
    最後に元の尺度の重みに戻して返す。balance は「誤り」側の重み。
    """
    mu = X[:, 1:].mean(axis=0)
    sd = X[:, 1:].std(axis=0) + 1e-9
    Z = np.hstack([np.ones((len(X), 1)), (X[:, 1:] - mu) / sd])
    penalty = l2 * np.eye(Z.shape[1])
    penalty[0, 0] = 0.0
    w = np.zeros(Z.shape[1])
    weight = y + balance * (1 - y)
    for _ in range(iterations):
        p = scoring.sigmoid(Z @ w)
        gradient = Z.T @ (p * weight - y) + penalty @ w
        hessian = (Z * (p * (1 - p) * weight)[:, None]).T @ Z + penalty
        step = np.linalg.solve(hessian, gradient)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    raw = np.empty_like(w)
    raw[1:] = w[1:] / sd
    raw[0] = w[0] - np.sum(w[1:] * mu / sd)
    return raw


def fit_linear(X, y, l2=1e-3):
    return np.linalg.solve(X.T @ X + l2 * np.eye(X.shape[1]), X.T @ y)


class Command(BaseCommand):
    help = 'Evaluate pronunciation scoring against human ratings (speechocean762).'

    def add_arguments(self, parser):
        parser.add_argument('--data-dir', required=True)
        parser.add_argument('--cache-dir', help='Cache model outputs here to speed up repeated runs')
        parser.add_argument('--fit', action='store_true', help='Fit calibration on the train split first')
        parser.add_argument('--save', action='store_true', help='Write the fitted calibration to calibration.json')
        parser.add_argument('--train-limit', type=int, default=1000)
        parser.add_argument('--test-limit', type=int, default=2500)

    def handle(self, *args, **options):
        import pandas as pd

        data_dir = Path(options['data_dir'])
        self.cache_dir = Path(options['cache_dir']) if options['cache_dir'] else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.assessor = PronunciationAssessor()

        def load(split, limit):
            path = data_dir / f'{split}.parquet'
            if not path.exists():
                raise CommandError(f'{path} not found')
            frame = pd.read_parquet(path)
            step = max(1, len(frame) // limit)
            return split, frame.iloc[::step][:limit]

        if options['fit']:
            train = self.collect(*load('train', options['train_limit']))
            self.fit(train)

        test = self.collect(*load('test', options['test_limit']))
        metrics = self.report(test)

        if options['save']:
            if not options['fit']:
                raise CommandError('--save requires --fit')
            self.save(metrics, train_size=options['train_limit'], test_size=len(test))

    # ------------------------------------------------------------------
    def logits_for(self, split, index, row):
        cache = self.cache_dir / f'{split}-{index}.npy' if self.cache_dir else None
        if cache and cache.exists():
            return np.load(cache).astype(np.float32)

        import librosa
        import soundfile as sf

        audio, rate = sf.read(io.BytesIO(row['audio']['bytes']), dtype='float32')
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if rate != acoustic.SAMPLE_RATE:
            audio = librosa.resample(audio, orig_sr=rate, target_sr=acoustic.SAMPLE_RATE)
        logits = acoustic.frame_logits(audio, self.assessor.model)
        if cache:
            np.save(cache, logits.astype(np.float16))
        return logits

    def collect(self, split, frame):
        """各発話について、音素の特徴量と人間の点数を集める"""
        utterances = []
        for count, (index, row) in enumerate(frame.iterrows(), start=1):
            posteriors = acoustic.posteriors_from_logits(self.logits_for(split, index, row), self.assessor.model)
            specs = [WordSpec(w['text'], [list(w['phones'])]) for w in row['words']]
            words = [_build_word(spec, i, spec.pronunciations[0]) for i, spec in enumerate(specs)]
            try:
                aligned = self.assessor._align(posteriors, words)
            except ValueError:
                continue
            rows = self.assessor.phone_features(posteriors, words, aligned)

            word_rows = []
            position = 0
            for i, word in enumerate(row['words']):
                labels = list(word['phones-accuracy'])
                vectors = [features.vector(bool(inserted)) for _, _, features, inserted in rows[position:position + len(labels)]]
                position += len(labels)
                word_rows.append({'X': np.array(vectors), 'y_phones': np.array(labels) / 2.0,
                                  'y_word': word['accuracy'] / 10.0})
            utterances.append({'words': word_rows, 'y': row['accuracy'] / 10.0})
            if count % 100 == 0:
                self.stdout.write(f'  {split}: {count}/{len(frame)}')
        return utterances

    def predict(self, utterance):
        word_scores, weights = [], []
        for word in utterance['words']:
            word['q_phones'] = scoring.sigmoid(word['X'] @ scoring.DETECTION_WEIGHTS)
            probabilities = scoring.sigmoid(word['X'] @ scoring.PHONE_WEIGHTS)
            word['p_phones'] = probabilities
            word['p_word'] = scoring.word_score(probabilities)
            word_scores.append(word['p_word'])
            weights.append(len(probabilities))
        utterance['p'] = scoring.sentence_score(word_scores, weights)

    def fit(self, utterances):
        X = np.vstack([w['X'] for u in utterances for w in u['words']])
        y = np.concatenate([w['y_phones'] for u in utterances for w in u['words']])
        scoring.PHONE_WEIGHTS = fit_logistic(X, y)
        scoring.DETECTION_WEIGHTS = fit_logistic(X, y, balance=scoring.DETECTION_BALANCE)
        scoring.DETECTION_THRESHOLD = self.choose_threshold(scoring.sigmoid(X @ scoring.DETECTION_WEIGHTS), y)
        self.stdout.write(f'  Detection threshold: {scoring.DETECTION_THRESHOLD:.2f}')

        for u in utterances:
            for w in u['words']:
                w['p_phones'] = scoring.sigmoid(w['X'] @ scoring.PHONE_WEIGHTS)
        WX = np.array([scoring.word_vector(w['p_phones']) for u in utterances for w in u['words']])
        Wy = np.array([w['y_word'] for u in utterances for w in u['words']])
        scoring.WORD_WEIGHTS = fit_linear(WX, Wy)

        SX, Sy = [], []
        for u in utterances:
            scores = [scoring.word_score(w['p_phones']) for w in u['words']]
            SX.append(scoring.sentence_vector(scores, [len(w['p_phones']) for w in u['words']]))
            Sy.append(u['y'])
        scoring.SENTENCE_WEIGHTS = fit_linear(np.array(SX), np.array(Sy))

        self.stdout.write(self.style.SUCCESS(f'Fitted on {len(utterances)} train utterances.'))

    @staticmethod
    def choose_threshold(quality, y):
        """適合率が DETECTION_MIN_PRECISION 以上の範囲で、最も多く誤りを拾えるしきい値"""
        mispronounced = y < 0.75
        best, best_recall = 0.5, -1.0
        for threshold in np.arange(0.30, 0.96, 0.01):
            flagged = quality < threshold
            if not flagged.any():
                continue
            precision = (flagged & mispronounced).sum() / flagged.sum()
            recall = (flagged & mispronounced).sum() / max(mispronounced.sum(), 1)
            if precision >= scoring.DETECTION_MIN_PRECISION and recall > best_recall:
                best, best_recall = float(threshold), recall
        return round(best, 2)

    def save(self, metrics, train_size, test_size):
        import json

        calibration = {
            'description': 'Calibration of pronunciation scores, fitted on speechocean762 '
                           '(https://huggingface.co/datasets/mispeech/speechocean762, Apache-2.0) '
                           'with `manage.py evaluate_pronunciation --fit --save`.',
            'train_utterances': train_size,
            'test_utterances': test_size,
            'test_metrics': metrics,
            'phone': {'features': scoring.FEATURE_NAMES,
                      'weights': [round(float(v), 6) for v in scoring.PHONE_WEIGHTS]},
            'phone_detection': {'features': scoring.FEATURE_NAMES,
                                'balance': scoring.DETECTION_BALANCE,
                                'threshold': scoring.DETECTION_THRESHOLD,
                                'weights': [round(float(v), 6) for v in scoring.DETECTION_WEIGHTS]},
            'word': {'features': ['bias', 'mean_phone', 'min_phone'],
                     'weights': [round(float(v), 6) for v in scoring.WORD_WEIGHTS]},
            'sentence': {'features': ['bias', 'mean_word', 'share_of_low_words'],
                         'weights': [round(float(v), 6) for v in scoring.SENTENCE_WEIGHTS]},
        }
        with open(scoring.CALIBRATION_PATH, 'w', encoding='utf-8') as f:
            json.dump(calibration, f, indent=2, ensure_ascii=False)
            f.write('\n')
        self.stdout.write(self.style.SUCCESS(f'Saved {scoring.CALIBRATION_PATH}'))

    def report(self, utterances):
        for u in utterances:
            self.predict(u)
        words = [w for u in utterances for w in u['words']]
        phone_pred = np.concatenate([w['p_phones'] for w in words])
        phone_true = np.concatenate([w['y_phones'] for w in words])
        gop = np.concatenate([w['X'][:, 2] for w in words])

        self.stdout.write(self.style.SUCCESS(f'Test utterances: {len(utterances)}, words: {len(words)}, phones: {len(phone_true)}'))
        self.stdout.write(f'  Phone    PCC: {pcc(phone_pred, phone_true):.3f}   (raw GOP only: {pcc(gop, phone_true):.3f})')
        self.stdout.write(f'  Word     PCC: {pcc([w["p_word"] for w in words], [w["y_word"] for w in words]):.3f}')
        self.stdout.write(f'  Sentence PCC: {pcc([u["p"] for u in utterances], [u["y"] for u in utterances]):.3f}')
        flagged = np.concatenate([w['q_phones'] for w in words]) < scoring.DETECTION_THRESHOLD
        mispronounced = phone_true < 0.75
        precision = float((flagged & mispronounced).sum() / max(flagged.sum(), 1))
        recall = float((flagged & mispronounced).sum() / max(mispronounced.sum(), 1))
        self.stdout.write(f'  Mispronunciation detection: precision {precision:.2f}, recall {recall:.2f} '
                          f'({mispronounced.mean():.1%} of phones are rated as mispronounced)')
        metrics = {
            'detection_precision': round(precision, 2),
            'detection_recall': round(recall, 2),
            'phone_pcc': round(pcc(phone_pred, phone_true), 3),
            'word_pcc': round(pcc([w['p_word'] for w in words], [w['y_word'] for w in words]), 3),
            'sentence_pcc': round(pcc([u['p'] for u in utterances], [u['y'] for u in utterances]), 3),
            'sentence_mae_0_10': round(float(np.mean(np.abs(
                np.array([u['p'] for u in utterances]) - np.array([u['y'] for u in utterances])))) * 10, 2),
        }
        self.stdout.write(f'  Sentence MAE (0-10): {metrics["sentence_mae_0_10"]:.2f}')
        return metrics
