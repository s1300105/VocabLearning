"""英語の音素（ARPAbet）と、音素認識モデルの出力記号（eSpeak 由来の IPA）の対応。

正解の音素列は CMU 発音辞書（ARPAbet）から作る。音素認識モデル
(facebook/wav2vec2-lv-60-espeak-cv-ft) は IPA の記号を出力するので、
ARPAbet の各音素について「正しい発音とみなすモデルの記号」の集合を定義する。
"""
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

VOWELS = {
    'AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'ER', 'EY', 'IH', 'IY', 'OW', 'OY', 'UH', 'UW',
}

# 正しい発音とみなすモデルの記号（強勢あり / なし共通）
ACCEPTABLE = {
    'AA': {'ɑː', 'ɑ', 'aː', 'ɒ'},
    'AE': {'æ'},
    'AH': {'ʌ', 'ə', 'ɐ'},
    'AO': {'ɔː', 'ɔ', 'ɑː', 'ɑ', 'ɒ'},  # 米語では cot / caught の区別がない話者が多い
    'AW': {'aʊ'},
    'AY': {'aɪ'},
    'EH': {'ɛ', 'e'},
    'ER': {'ɜː', 'ɚ', 'ɜ'},
    'EY': {'eɪ', 'eː'},
    'IH': {'ɪ', 'ᵻ'},
    'IY': {'iː', 'i'},
    'OW': {'oʊ', 'əʊ', 'oː'},
    'OY': {'ɔɪ', 'oɪ'},
    'UH': {'ʊ'},
    'UW': {'uː', 'u'},
    'B': {'b'},
    'CH': {'tʃ'},
    'D': {'d', 'ɾ'},  # ladder の d は弾き音になる
    'DH': {'ð'},
    'F': {'f'},
    'G': {'ɡ'},
    'HH': {'h'},
    'JH': {'dʒ'},
    'K': {'k'},
    'L': {'l', 'ɫ', 'l̩'},
    'M': {'m'},
    'N': {'n', 'n̩'},
    'NG': {'ŋ'},
    'P': {'p'},
    'R': {'ɹ', 'ɻ'},
    'S': {'s'},
    'SH': {'ʃ'},
    'T': {'t', 'ɾ', 'ʔ'},  # water の t は弾き音、button の t は声門閉鎖音になる
    'TH': {'θ'},
    'V': {'v'},
    'W': {'w'},
    'Y': {'j'},
    'Z': {'z'},
    'ZH': {'ʒ'},
}

# 弱く発音される母音（強勢 0）は曖昧母音になりやすいので広めに許容する
REDUCED_EXTRA = {
    'AH': {'ᵻ', 'ɪ', 'ɚ'},
    'IH': {'ə', 'i', 'ɐ'},
    'IY': {'ɪ', 'ᵻ'},
    'UW': {'ʊ', 'ə'},
    'OW': {'ə', 'oʊ'},
    'ER': {'ə'},
    'EH': {'ɪ', 'ə'},
    'AA': {'ə', 'ɐ'},
    'AO': {'ə'},
    'AE': {'ə', 'ɐ'},
    'EY': {'ɪ', 'ə'},
}

# モデルが「母音 + r」などをまとめて1記号で出す場合の記号
COMBINED_TOKENS = {
    ('AA', 'R'): {'ɑːɹ'},
    ('AO', 'R'): {'ɔːɹ', 'oːɹ'},
    ('OW', 'R'): {'oːɹ', 'ɔːɹ'},
    ('IH', 'R'): {'ɪɹ'},
    ('IY', 'R'): {'ɪɹ'},
    ('EH', 'R'): {'ɛɹ'},
    ('EY', 'R'): {'ɛɹ'},
    ('UH', 'R'): {'ʊɹ'},
    ('UW', 'R'): {'ʊɹ'},
    ('AY', 'ER'): {'aɪɚ', 'aɪə'},
    ('AH', 'L'): {'əl'},
}

# 英語以外で、学習者の誤りとして現れやすい音（日本語のラ行の弾き音、唇を丸めない「ウ」、「フ」の子音など）
L2_TOKENS = {
    'a', 'aː', 'o', 'e', 'i', 'u', 'ɯ', 'ɨ', 'y', 'ø',
    'ɾ', 'r', 'ʁ', 'ɸ', 'β', 'ç', 'x', 'ɣ', 'ʋ', 'ɕ', 'tɕ', 'dʑ', 'ts', 'ʔ', 'ɴ', 'ɲ',
}


def model_inventory() -> frozenset:
    """音素認識モデルの出力のうち、採点に使う記号。

    多言語モデルなので、そのままだと中国語の声調付き母音などに確率が流れて
    英語として問題のない音まで「別の音」と判定してしまう。英語の音素と、
    学習者の誤りとしてよく現れる音だけに絞ってから確率を計算する。
    """
    tokens = set(L2_TOKENS)
    for group in (ACCEPTABLE, REDUCED_EXTRA, COMBINED_TOKENS):
        for value in group.values():
            tokens |= value
    return frozenset(tokens)


# 学習者向けの表示用 IPA
DISPLAY_IPA = {
    'AA': 'ɑ', 'AE': 'æ', 'AH': 'ʌ', 'AO': 'ɔ', 'AW': 'aʊ', 'AY': 'aɪ', 'EH': 'ɛ', 'ER': 'ɝ',
    'EY': 'eɪ', 'IH': 'ɪ', 'IY': 'i', 'OW': 'oʊ', 'OY': 'ɔɪ', 'UH': 'ʊ', 'UW': 'u',
    'B': 'b', 'CH': 'tʃ', 'D': 'd', 'DH': 'ð', 'F': 'f', 'G': 'g', 'HH': 'h', 'JH': 'dʒ', 'K': 'k',
    'L': 'l', 'M': 'm', 'N': 'n', 'NG': 'ŋ', 'P': 'p', 'R': 'r', 'S': 's', 'SH': 'ʃ', 'T': 't',
    'TH': 'θ', 'V': 'v', 'W': 'w', 'Y': 'j', 'Z': 'z', 'ZH': 'ʒ',
}
REDUCED_DISPLAY = {'AH': 'ə', 'ER': 'ɚ'}

# モデルの記号を学習者向けに表示するときの置き換え
TOKEN_DISPLAY = {'ɹ': 'r', 'ɻ': 'r', 'ɡ': 'g', 'ɫ': 'l', 'l̩': 'l', 'n̩': 'n', 'ᵻ': 'ɪ', 'ɐ': 'ə'}

# 数字（"10" など）も1語として扱う。辞書にないので採点はせず、その部分の音声を吸収させる
WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*|\d+(?:[.,]\d+)*")


def split_phone(phone: str) -> Tuple[str, Optional[int]]:
    """'AH0' -> ('AH', 0)、'K' -> ('K', None)"""
    match = re.fullmatch(r'([A-Z]+)([0-2])?', phone.upper())
    if not match:
        raise ValueError(f'Unknown ARPAbet phone: {phone}')
    base, stress = match.groups()
    if base not in ACCEPTABLE:
        raise ValueError(f'Unknown ARPAbet phone: {phone}')
    return base, (int(stress) if stress is not None else None)


def acceptable_tokens(phone: str) -> frozenset:
    base, stress = split_phone(phone)
    tokens = set(ACCEPTABLE[base])
    if base in VOWELS and stress == 0:
        tokens |= REDUCED_EXTRA.get(base, set())
    return frozenset(tokens)


def display_phone(phone: str) -> str:
    base, stress = split_phone(phone)
    if stress == 0 and base in REDUCED_DISPLAY:
        return REDUCED_DISPLAY[base]
    return DISPLAY_IPA[base]


def display_token(token: Optional[str]) -> Optional[str]:
    if token is None:
        return None
    return TOKEN_DISPLAY.get(token, token)


@dataclass
class PhoneSpec:
    """1つの音素の採点対象"""
    phone: str                # ARPAbet（強勢付き可）
    acceptable: frozenset     # 正しいとみなすモデルの記号

    @property
    def base(self) -> str:
        return split_phone(self.phone)[0]

    @property
    def is_vowel(self) -> bool:
        return self.base in VOWELS


@dataclass
class Unit:
    """アライメントの単位。通常は1音素、「母音 + r」などは2音素をまとめて1単位にする。"""
    phones: List[PhoneSpec]
    word_index: int
    wildcard: bool = False    # 辞書にない単語: どの記号でも受け入れて音声を吸収する

    @property
    def acceptable(self) -> frozenset:
        tokens = set()
        for p in self.phones:
            tokens |= p.acceptable
        return frozenset(tokens)

    @property
    def label(self):
        """CTC で「同じラベルが連続する」かどうかの判定用"""
        return ('*',) if self.wildcard else tuple(p.phone for p in self.phones)


@dataclass
class WordSpec:
    text: str
    pronunciations: List[List[str]] = field(default_factory=list)  # 空なら辞書にない単語

    @property
    def in_lexicon(self) -> bool:
        return bool(self.pronunciations)


def build_units(phones: Sequence[str], word_index: int) -> List[Unit]:
    """1単語分の ARPAbet 列をアライメント単位に変換する"""
    units: List[Unit] = []
    i = 0
    while i < len(phones):
        base = split_phone(phones[i])[0]
        if i + 1 < len(phones):
            next_base = split_phone(phones[i + 1])[0]
            combined = COMBINED_TOKENS.get((base, next_base))
            # AH + L をまとめるのは語末の弱母音（little の -tle）だけ
            if combined and (base, next_base) == ('AH', 'L'):
                is_syllabic = split_phone(phones[i])[1] == 0 and i + 2 == len(phones)
                combined = combined if is_syllabic else None
            if combined:
                first = PhoneSpec(phones[i], acceptable_tokens(phones[i]) | combined)
                second = PhoneSpec(phones[i + 1], acceptable_tokens(phones[i + 1]) | combined)
                units.append(Unit([first, second], word_index))
                i += 2
                continue
        units.append(Unit([PhoneSpec(phones[i], acceptable_tokens(phones[i]))], word_index))
        i += 1
    return units


@lru_cache(maxsize=1)
def _cmudict():
    from conversation_analysis.vocab_diversity_analysis import ensure_nltk_resource

    ensure_nltk_resource('corpora/cmudict', 'cmudict')
    from nltk.corpus import cmudict

    return cmudict.dict()


def lookup(word: str) -> List[List[str]]:
    """CMU 発音辞書で単語の発音（複数あり得る）を引く"""
    return [list(p) for p in _cmudict().get(word.lower(), [])]


def words_from_text(text: str) -> List[WordSpec]:
    return [WordSpec(text=w, pronunciations=lookup(w)) for w in WORD_RE.findall(text or '')]
