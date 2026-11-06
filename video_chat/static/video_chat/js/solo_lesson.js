// 一人用レッスン: ブラウザのマイクで録音し、サーバーに送って文字起こし・分析する
document.addEventListener('DOMContentLoaded', () => {
    const readJson = id => JSON.parse(document.getElementById(id).textContent);
    const PROMPT = readJson('solo-prompt');
    const MODE = readJson('solo-mode');
    const MAX_SECONDS = readJson('solo-max-seconds');
    const MIN_SECONDS = readJson('solo-min-seconds');
    const CSRF_TOKEN = document.querySelector('[name=csrfmiddlewaretoken]').value;

    const startButton = document.getElementById('start-button');
    const stopButton = document.getElementById('stop-button');
    const retryButton = document.getElementById('retry-button');
    const submitButton = document.getElementById('submit-button');
    const newTopicLink = document.getElementById('new-topic');
    const preview = document.getElementById('preview');
    const timer = document.getElementById('timer');
    const status = document.getElementById('status');

    let mediaRecorder = null;
    let stream = null;
    let chunks = [];
    let recordedBlob = null;
    let recordedSeconds = 0;
    let startedAt = 0;
    let timerId = null;
    let previewUrl = null;

    function setStatus(message, isError = false) {
        status.textContent = message;
        status.classList.toggle('error', isError);
    }

    function formatTime(seconds) {
        const s = Math.floor(seconds);
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    }

    function show(...elements) { elements.forEach(el => { el.hidden = false; }); }
    function hide(...elements) { elements.forEach(el => { el.hidden = true; }); }

    function pickMimeType() {
        // ブラウザごとに対応形式が違う（Safari は mp4）。サーバー側で WAV に変換する
        const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
        return candidates.find(type => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || '';
    }

    function extensionFor(mimeType) {
        if (mimeType.includes('mp4')) return 'mp4';
        if (mimeType.includes('ogg')) return 'ogg';
        return 'webm';
    }

    function releaseMicrophone() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
    }

    async function startRecording() {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            setStatus('Recording is not supported in this browser. Open this page over HTTPS or on localhost.', true);
            return;
        }

        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (error) {
            setStatus('Could not access the microphone. Please allow microphone access and try again.', true);
            return;
        }

        const mimeType = pickMimeType();
        mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        chunks = [];

        mediaRecorder.addEventListener('dataavailable', event => {
            if (event.data.size > 0) chunks.push(event.data);
        });
        mediaRecorder.addEventListener('stop', onRecordingStopped);

        mediaRecorder.start();
        startedAt = Date.now();
        timer.textContent = formatTime(0);
        timerId = setInterval(() => {
            const elapsed = (Date.now() - startedAt) / 1000;
            timer.textContent = formatTime(elapsed);
            if (elapsed >= MAX_SECONDS) {
                setStatus(`Reached the ${MAX_SECONDS}-second limit.`);
                stopRecording();
            }
        }, 250);

        hide(startButton, retryButton, submitButton, preview);
        show(stopButton);
        newTopicLink.classList.add('disabled');
        timer.classList.add('recording');
        setStatus(MODE === 'read' ? 'Recording… read the sentence aloud.' : 'Recording… speak about the topic.');
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
        clearInterval(timerId);
        timer.classList.remove('recording');
    }

    function onRecordingStopped() {
        releaseMicrophone();
        recordedSeconds = (Date.now() - startedAt) / 1000;
        recordedBlob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });

        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = URL.createObjectURL(recordedBlob);
        preview.src = previewUrl;

        hide(stopButton);
        show(retryButton, preview);
        newTopicLink.classList.remove('disabled');

        if (recordedSeconds < MIN_SECONDS) {
            setStatus(`The recording is too short. Please speak for at least ${MIN_SECONDS} seconds.`, true);
            return;
        }
        show(submitButton);
        setStatus(`Listen to your recording, then press "${submitButton.textContent.trim()}".`);
    }

    async function submitRecording() {
        if (!recordedBlob) return;

        submitButton.disabled = true;
        retryButton.disabled = true;
        setStatus(MODE === 'read' ? 'Uploading your recording…' : 'Transcribing your speech… this can take a minute.');

        const formData = new FormData();
        const mimeType = recordedBlob.type || 'audio/webm';
        formData.append('audio', recordedBlob, `recording.${extensionFor(mimeType)}`);
        formData.append('prompt', PROMPT);
        formData.append('mode', MODE);

        try {
            const response = await fetch(window.SOLO_UPLOAD_URL, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF_TOKEN },
                body: formData,
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status !== 'success') {
                throw new Error(data.error || `Upload failed (status ${response.status})`);
            }
            window.location.href = data.next_url;
        } catch (error) {
            setStatus(`Error: ${error.message}`, true);
            submitButton.disabled = false;
            retryButton.disabled = false;
        }
    }

    startButton.addEventListener('click', startRecording);
    stopButton.addEventListener('click', stopRecording);
    retryButton.addEventListener('click', startRecording);
    submitButton.addEventListener('click', submitRecording);
    newTopicLink.addEventListener('click', event => {
        if (newTopicLink.classList.contains('disabled')) event.preventDefault();
    });
    window.addEventListener('beforeunload', releaseMicrophone);
});
