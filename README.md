# VocabLearning

英語学習用の Django アプリです。

| アプリ | 内容 |
|---|---|
| `word_learning` | 単語帳・単語クイズ（CEFR レベル別）、ローカル LLM による例文生成と英作文の出題・採点 |
| `video_chat` | Twilio Video による講師と生徒のビデオレッスンと、一人で話して録音する一人用レッスン。生徒の音声を Whisper で文字起こし |
| `conversation_analysis` | 文字起こしの語彙分析（頻出語・品詞・MTLD）、類義語の提案、音素レベルの発音チェック |
| `english_conversation` | OpenAI Realtime API を使った会話練習（開発途中のため、現在は `INSTALLED_APPS` に含まれていません） |

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

`ffmpeg` も必要です（音声変換に使用）。

発音チェックで使う音素認識モデル（約1.3GB）は、初回の発音チェック時に自動でダウンロードされます。
事前に取得しておく場合は次を実行してください。

```bash
python manage.py prepare_pronunciation_model
```

```bash
cp .env.example .env   # 値を埋める（DJANGO_SECRET_KEY, Twilio, OpenAI など）
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- ログイン後のトップ: `/word_learning/`
- ビデオレッスン: `/video_chat/video_lesson/`
- 一人用レッスン: `/video_chat/solo/`（CEFR レベルに合ったお題について話し、ブラウザのマイクで録音）
  - 「Read aloud」（音読モード）: 表示された文を読み上げると、その文を正解として音素ごとに発音をチェックする（文字起こしの API も使わない）
- 録音一覧: `/video_chat/recordings/`

一人用レッスンの録音は `private_media/` に保存され、本人だけが再生できます。
ブラウザのマイクは HTTPS か `localhost` でしか使えないので、外部端末からは ngrok などで HTTPS 公開してください。
お題は `video_chat/topics.py` で編集できます。

Twilio のビデオ通話を外部端末から試す場合は ngrok などで HTTPS 公開してください（`*.ngrok-free.app` は許可済み）。

## 発音チェックの仕組み

外部 API は使わず、サーバー上で動く音素認識モデル
（[facebook/wav2vec2-lv-60-espeak-cv-ft](https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft)、Apache-2.0）で採点します。

1. 正解の文（音読モードでは読んだ文、自由に話したときは文字起こし）を CMU 発音辞書で音素列にする
2. モデルで録音の各瞬間がどの音らしいかを求め、CTC の強制アライメントで音素ごとの区間を決める
3. 音素ごとに GOP（正しい音らしさと、ほかの音らしさの比較）と、アライメントに依存しない GOP
   （その音を別の音に置き換えた・抜かした場合との尤度比）を計算し、点数に換算する
4. r と l、th、v と b、æ、母音の挿入（street →「ストリート」）など、日本語話者に多い誤りに日本語でアドバイスする

点数への換算係数は、専門家が採点した公開データセット
[speechocean762](https://huggingface.co/datasets/mispeech/speechocean762)（Apache-2.0）で学習しています。
評価データ（2,500 発話、47,369 音素）での人間の採点との相関（PCC）は次のとおりです。

| 単位 | PCC |
|---|---|
| 音素 | 0.52 |
| 単語 | 0.51 |
| 文 | 0.62（平均誤差 0.91 点 / 10 点満点） |

「要練習」と判定した音素のうち、採点者も誤りとしたものは 45%、採点者が誤りとした音素の 40% を検出しています。
評価データの話者は中国語話者なので、日本語話者に対する精度とは異なる可能性があります。

精度の確認と係数の再学習は次のコマンドで行えます（データセットの parquet を `train.parquet` / `test.parquet` として置く）。

```bash
python manage.py evaluate_pronunciation --data-dir path/to/speechocean762 --fit
```

## テスト

```bash
python manage.py test
```

## 注意

- `.env`、`db.sqlite3`、`media/`、`private_media/`、`temp_audio/`、`logs/` には秘密情報や録音などの個人データが入るため、Git にはコミットしません（`.gitignore` 済み）。
- 録音ルールは identity が `student` の参加者の音声だけを録音する設定のため、1 ルームにつき生徒 1 人を前提としています。
