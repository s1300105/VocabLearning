// 発音チェック: サーバーで音素ごとに採点した結果を表示する
document.addEventListener('DOMContentLoaded', () => {
    const ROOM_SID = JSON.parse(document.getElementById('room-sid-data').textContent);
    const CSRF_TOKEN = document.querySelector('[name=csrfmiddlewaretoken]').value;
    const URLS = window.PRONUNCIATION_URLS;

    const $ = id => document.getElementById(id);
    const learnerAudio = $('learner-audio');
    let stopAt = null;
    let selectedChip = null;

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function post(url) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: `room_sid=${encodeURIComponent(ROOM_SID)}`,
        }).then(async response => {
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || `Request failed (status ${response.status})`);
            return data;
        });
    }

    // 学習者の録音の一部（単語）だけを再生する
    function playSegment(start, end) {
        if (!learnerAudio.src) return;
        stopAt = end;
        learnerAudio.currentTime = Math.max(0, start - 0.05);
        learnerAudio.play();
    }
    learnerAudio.addEventListener('timeupdate', () => {
        if (stopAt !== null && learnerAudio.currentTime >= stopAt) {
            learnerAudio.pause();
            stopAt = null;
        }
    });

    function renderSummary(result) {
        $('overall-score').textContent = result.score;
        $('overall-score').className = `overall-score ${result.grade}`;
        $('speed').textContent = `${result.fluency.words_per_minute} words/min`;
        $('pauses').textContent = result.fluency.long_pauses === 0
            ? 'None'
            : `${result.fluency.long_pauses} (${result.fluency.long_pause_seconds}s)`;
        $('checked').textContent = `${result.scored_words} / ${result.words.length}`;
        $('summary').hidden = false;
    }

    function renderWords(result) {
        const container = $('word-chips');
        container.replaceChildren(...result.words.map(word => {
            const chip = el('button', `word-chip ${word.grade}`, word.text);
            chip.type = 'button';
            chip.title = word.scored ? `${word.score} points` : 'Not in the pronunciation dictionary';
            chip.disabled = !word.scored;
            chip.addEventListener('click', () => showDetail(word, chip));
            return chip;
        }));
    }

    function showDetail(word, chip) {
        if (selectedChip) selectedChip.classList.remove('selected');
        selectedChip = chip;
        chip.classList.add('selected');

        $('detail-word').textContent = word.text;
        $('detail-score').textContent = word.score;
        $('detail-score').className = `score-badge ${word.grade}`;
        $('detail-play').onclick = () => playSegment(word.start, word.end);

        $('detail-phones').replaceChildren(...word.phones.map(phone => {
            const item = el('li', `phone ${phone.grade}`);
            item.append(el('span', 'ipa', `/${phone.ipa}/`), el('span', 'phone-score', phone.score));
            item.title = phone.heard ? `Heard as /${phone.heard}/` : '';
            return item;
        }));

        const messages = word.phones.filter(p => p.message).map(p => el('li', '', p.message));
        $('detail-messages').replaceChildren(...messages);
        $('word-detail').hidden = false;
        playSegment(word.start, word.end);
    }

    function renderIssues(result) {
        const list = $('issues');
        list.replaceChildren(...result.issues.map(issue => {
            const item = el('li', 'issue');
            const head = el('div', 'issue-head');
            head.append(
                el('strong', '', issue.word),
                el('span', `score-badge ${issue.grade}`, `/${issue.ipa}/ ${issue.score}`),
            );
            const play = el('button', 'play-button', '▶');
            play.type = 'button';
            play.setAttribute('aria-label', `Play "${issue.word}"`);
            play.addEventListener('click', () => playSegment(issue.start, issue.end));
            head.append(play);
            item.append(head, el('p', 'issue-message', issue.message));
            return item;
        }));
        $('no-issues').hidden = result.issues.length > 0;
        $('issues-section').hidden = false;
    }

    async function analyze() {
        try {
            const result = await post(URLS.analyze);
            learnerAudio.src = result.learner_audio_url;
            renderSummary(result);
            renderWords(result);
            renderIssues(result);
            $('status').textContent = 'Tap a word to see each sound and hear your voice.';
        } catch (error) {
            $('status').textContent = `Error: ${error.message}`;
            $('status').classList.add('error');
        }
    }

    $('model-button').addEventListener('click', async () => {
        const button = $('model-button');
        button.disabled = true;
        $('model-status').textContent = 'Preparing the model voice…';
        try {
            const data = await post(URLS.modelVoice);
            $('model-audio').src = data.model_audio_url;
            $('model-audio').hidden = false;
            $('model-status').textContent = '';
            button.hidden = true;
        } catch (error) {
            $('model-status').textContent = `Error: ${error.message}`;
            button.disabled = false;
        }
    });

    analyze();
});
