"""音素レベルの発音評価エンジンのテスト。

本物の音素認識モデル（約1.3GB）は使わず、小さな記号表と合成した確率行列で動作を確かめる。
"""
import itertools
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from .pronunciation import scoring
from .pronunciation.acoustic import AcousticModel
from .pronunciation.alignment import batched_ctc_log_likelihood, forced_align
from .pronunciation.assessor import PronunciationAssessor
from .pronunciation.phonemes import WordSpec, build_units, words_from_text

VOCAB = ['<pad>', 'k', 'ɑː', 'ɹ', 'ɑːɹ', 'l', 'ɾ', 'aɪ', 's', 't', 'iː', 'ɯ', 'ə', 'ð', 'z', 'ɪ', 'n']
BLANK = 0


def fake_model():
    return AcousticModel(model=None, feature_extractor=None, vocab=VOCAB, blank_id=BLANK,
                         allowed_mask=np.ones(len(VOCAB), dtype=bool))


def posteriors(tokens, frames_per_token=3, gap=2, confidence=0.95):
    """記号列から、CTC らしい（記号のフレームとブランクのフレームが交互の）確率行列を作る"""
    rows = []

    def frame(token_id):
        row = np.full(len(VOCAB), (1 - confidence) / (len(VOCAB) - 1))
        row[token_id] = confidence
        rows.append(row)

    for _ in range(gap):
        frame(BLANK)
    for token in tokens:
        for _ in range(frames_per_token):
            frame(VOCAB.index(token))
        for _ in range(gap):
            frame(BLANK)
    return np.array(rows)


def assess(tokens, words):
    assessor = PronunciationAssessor(model=fake_model())
    return assessor.assess(posteriors(tokens), words)


class PhonemeTests(SimpleTestCase):
    def test_vowel_and_r_are_merged_into_one_unit(self):
        units = build_units(['K', 'AA1', 'R'], 0)
        self.assertEqual([[p.phone for p in u.phones] for u in units], [['K'], ['AA1', 'R']])
        self.assertIn('ɑːɹ', units[1].acceptable)

    def test_syllabic_l_only_merged_at_word_end(self):
        little = build_units(['L', 'IH1', 'T', 'AH0', 'L'], 0)
        self.assertEqual(len(little[-1].phones), 2)
        alone = build_units(['AH0', 'L', 'AW1'], 0)  # allow
        self.assertEqual(len(alone[0].phones), 1)

    def test_reduced_vowels_are_more_lenient(self):
        stressed = build_units(['AH1'], 0)[0].acceptable
        reduced = build_units(['AH0'], 0)[0].acceptable
        self.assertTrue(stressed < reduced)

    def test_words_from_text_marks_unknown_words(self):
        fake_dict = {'i': [['AY1']], 'like': [['L', 'AY1', 'K']]}
        with mock.patch('conversation_analysis.pronunciation.phonemes._cmudict', return_value=fake_dict):
            words = words_from_text("I like Pokémon!")
        self.assertEqual([w.text for w in words], ['I', 'like', 'Pok', 'mon'])
        self.assertEqual([w.in_lexicon for w in words], [True, True, False, False])

    def test_numbers_are_kept_as_unscored_words(self):
        with mock.patch('conversation_analysis.pronunciation.phonemes._cmudict', return_value={'i': [['AY1']]}):
            words = words_from_text("I have 10 cats, 3.5 kg")
        self.assertIn('10', [w.text for w in words])
        self.assertIn('3.5', [w.text for w in words])
        self.assertFalse(next(w for w in words if w.text == '10').in_lexicon)


class AlignmentTests(SimpleTestCase):
    def test_forced_align_finds_each_unit(self):
        post = posteriors(['k', 'ɑː', 's'])
        ids = [[VOCAB.index('k')], [VOCAB.index('ɑː')], [VOCAB.index('s')]]
        emissions = np.log(np.stack([post[:, i].sum(axis=1) for i in ids], axis=1))
        aligned = forced_align(emissions, np.log(post[:, BLANK]), ['K', 'AA', 'S'])

        # 各記号は gap(2) フレームのあとに 3 フレームずつ並んでいる
        self.assertEqual([(a.first_emission, a.last_emission) for a in aligned], [(2, 4), (7, 9), (12, 14)])

    def test_too_short_audio_raises(self):
        with self.assertRaises(ValueError):
            forced_align(np.zeros((1, 2)), np.zeros(1), ['A', 'B'])

    def test_ctc_likelihood_matches_brute_force(self):
        rng = np.random.default_rng(0)
        T, V = 4, 3  # 記号: 0=ブランク, 1, 2
        probs = rng.dirichlet(np.ones(V), size=T)
        labels = [1, 1]  # 同じ記号が続く場合はブランクを挟む必要がある

        def collapse(path):
            out = []
            for i, p in enumerate(path):
                if p != 0 and (i == 0 or p != path[i - 1]):
                    out.append(p)
            return out

        brute = sum(np.prod([probs[t, p] for t, p in enumerate(path)])
                    for path in itertools.product(range(V), repeat=T) if collapse(path) == labels)

        emissions = np.log(probs[:, labels])[None]
        same = np.array([[False, True]])
        ll = batched_ctc_log_likelihood(emissions, np.log(probs[:, 0]), same)[0]
        self.assertAlmostEqual(float(np.exp(ll)), float(brute), places=10)


class AssessorTests(SimpleTestCase):
    RICE = [WordSpec('rice', [['R', 'AY1', 'S']])]

    def phones(self, result, word=0):
        return result['words'][word]['phones']

    def test_correct_pronunciation_scores_high(self):
        result = assess(['ɹ', 'aɪ', 's'], self.RICE)
        self.assertGreaterEqual(result['score'], 80)
        self.assertEqual(result['issues'], [])
        self.assertTrue(all(p['issue'] is None for p in self.phones(result)))

    def test_r_pronounced_as_l_is_reported_with_tip(self):
        good = assess(['ɹ', 'aɪ', 's'], self.RICE)
        bad = assess(['l', 'aɪ', 's'], self.RICE)

        r = self.phones(bad)[0]
        self.assertEqual(r['issue'], 'substitution')
        self.assertEqual(r['heard'], 'l')
        self.assertIn('r は舌先', r['message'])
        self.assertLess(r['score'], self.phones(good)[0]['score'])
        self.assertLess(bad['score'], good['score'])
        self.assertEqual(bad['issues'][0]['word'], 'rice')

    def test_japanese_flap_r_is_detected(self):
        r = self.phones(assess(['ɾ', 'aɪ', 's'], self.RICE))[0]
        self.assertEqual(r['issue'], 'substitution')
        self.assertEqual(r['heard'], 'ɾ')

    def test_vowel_inserted_after_final_consonant(self):
        # "rice" を「ライス」のように最後に母音を付けて発音
        result = assess(['ɹ', 'aɪ', 's', 'ɯ'], self.RICE)
        s = self.phones(result)[-1]
        self.assertEqual(s['issue'], 'inserted_vowel')
        self.assertIn('母音', s['message'])

    def test_dropped_r_after_vowel(self):
        car = [WordSpec('car', [['K', 'AA1', 'R']])]
        good = self.phones(assess(['k', 'ɑːɹ'], car))
        dropped = self.phones(assess(['k', 'ɑː'], car))
        self.assertIsNone(good[2]['issue'])
        self.assertLess(dropped[2]['score'], good[2]['score'])
        self.assertIsNotNone(dropped[2]['issue'])

    def test_unknown_word_is_skipped_but_others_are_scored(self):
        words = [WordSpec('xyz', []), WordSpec('rice', [['R', 'AY1', 'S']])]
        result = assess(['t', 'ə', 'ɹ', 'aɪ', 's'], words)
        self.assertFalse(result['words'][0]['scored'])
        self.assertIsNone(result['words'][0]['score'])
        self.assertTrue(result['words'][1]['scored'])
        self.assertEqual(result['unscored_words'], ['xyz'])
        self.assertGreaterEqual(result['words'][1]['score'], 80)

    def test_best_dictionary_variant_is_used(self):
        # "the" は辞書に ðə と ðiː の2通りがある
        the = [WordSpec('the', [['DH', 'AH0'], ['DH', 'IY0']])]
        result = assess(['ð', 'iː'], the)
        self.assertEqual([p['phone'] for p in self.phones(result)], ['DH', 'IY0'])
        self.assertTrue(all(p['issue'] is None for p in self.phones(result)))

    def test_word_timing_and_fluency(self):
        result = assess(['ɹ', 'aɪ', 's'], self.RICE)
        word = result['words'][0]
        self.assertAlmostEqual(word['start'], 0.04)  # 最初の記号は 2 フレーム目（20ms × 2）
        self.assertGreater(word['end'], word['start'])
        self.assertEqual(result['fluency']['long_pauses'], 0)

    def test_empty_text_raises(self):
        with self.assertRaises(ValueError):
            assess(['ɹ'], [])


class ScoringTests(SimpleTestCase):
    def test_scores_stay_in_range(self):
        self.assertTrue(0 <= scoring.word_score([0.0, 0.0]) <= 1)
        self.assertTrue(0 <= scoring.word_score([1.0, 1.0]) <= 1)
        self.assertTrue(0 <= scoring.sentence_score([1.0, 0.2], [3, 2]) <= 1)
        self.assertEqual(scoring.sentence_score([], []), 0.0)


class AcousticThreadingTests(SimpleTestCase):
    """Web サーバーはリクエストごとに別スレッドで処理するので、どのスレッドからでも推論できること"""

    def test_inference_works_from_another_thread(self):
        try:
            import torch
        except ImportError:
            self.skipTest('torch is not installed')
        import threading

        from .pronunciation import acoustic

        class TinyModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.linear = torch.nn.Linear(1, len(VOCAB))

            def forward(self, input_values):
                frames = input_values[:, ::320].unsqueeze(-1)
                return type('Output', (), {'logits': self.linear(frames)})()

        model = fake_model()
        model.model = TinyModel()
        model.feature_extractor = lambda audio, sampling_rate, return_tensors: type(
            'Inputs', (), {'input_values': torch.tensor(audio).unsqueeze(0)})()

        results = []
        thread = threading.Thread(target=lambda: results.append(
            acoustic.frame_posteriors(np.zeros(16000, dtype=np.float32), model)))
        thread.start()
        thread.join()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].shape[1], len(VOCAB))
        self.assertTrue(np.allclose(results[0].sum(axis=1), 1.0))
