# VocabLearning

英語学習用の Django アプリです。

| アプリ | 内容 |
|---|---|
| `word_learning` | 単語帳・単語クイズ（CEFR レベル別）、ローカル LLM による例文生成と英作文の出題・採点 |
| `video_chat` | Twilio Video による講師と生徒のビデオレッスン。生徒の音声を録音し、Whisper で文字起こし |
| `conversation_analysis` | 文字起こしの語彙分析（頻出語・品詞・MTLD）、類義語の提案、お手本音声（TTS）との発音比較 |
| `english_conversation` | OpenAI Realtime API を使った会話練習（開発途中のため、現在は `INSTALLED_APPS` に含まれていません） |

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

`ffmpeg` も必要です（音声変換に使用）。

```bash
cp .env.example .env   # 値を埋める（DJANGO_SECRET_KEY, Twilio, OpenAI など）
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- ログイン後のトップ: `/word_learning/`
- ビデオレッスン: `/video_chat/video_lesson/`
- 録音一覧: `/video_chat/recordings/`

Twilio のビデオ通話を外部端末から試す場合は ngrok などで HTTPS 公開してください（`*.ngrok-free.app` は許可済み）。

## テスト

```bash
python manage.py test
```

## 注意

- `.env`、`db.sqlite3`、`media/`、`temp_audio/`、`logs/` には秘密情報や録音などの個人データが入るため、Git にはコミットしません（`.gitignore` 済み）。
- 録音ルールは identity が `student` の参加者の音声だけを録音する設定のため、1 ルームにつき生徒 1 人を前提としています。
