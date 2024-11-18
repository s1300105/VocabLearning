document.addEventListener('DOMContentLoaded', function() {
    const textInput = document.getElementById('text-input');
    const generateBtn = document.getElementById('generate-btn');
    const referenceAudioPlayer = document.getElementById('reference-audio-player');
    const recordingAudioPlayer = document.getElementById('recording-audio-player');
    const message = document.getElementById('message');

    generateBtn.addEventListener('click', async function() {
        const text = textInput.value.trim();
        if (!text) {
            message.textContent = 'Please enter some text';
            return;
        }

        try {
            message.textContent = 'Generating audio...';
            const response = await fetch('/conversation_analysis/audio-analysis/generate-audio/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `text=${encodeURIComponent(text)}`
            });

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }

            // レファレンスオーディオを設定
            const referenceFilename = data.audio_path.split('/').pop();
            referenceAudioPlayer.src = `/conversation_analysis/audio-analysis/get-audio/${referenceFilename}`;
            await referenceAudioPlayer.load();

            // 録音オーディオを設定
            const recordingFilename = data.audio_path_recorded.split('/').pop();
            recordingAudioPlayer.src = `/conversation_analysis/audio-analysis/get-audio/${recordingFilename}`;
            await recordingAudioPlayer.load();

            message.textContent = '';
        } catch (error) {
            message.textContent = `Error: ${error.message}`;
        }
    });
});