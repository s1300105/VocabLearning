// video_chat/static/video_chat/js/transcribe.js

document.addEventListener('DOMContentLoaded', function() {
    initializeAudioPlayer();
    formatTranscriptText();
    setupDownloadButton();
});

function initializeAudioPlayer() {
    const audioPlayer = document.querySelector('audio');
    if (audioPlayer) {
        audioPlayer.addEventListener('error', function(e) {
            console.error('Error loading audio:', e);
            alert('Error loading audio file');
        });

        audioPlayer.addEventListener('loadeddata', function() {
            console.log('Audio loaded successfully');
        });
    }
}

function formatTranscriptText() {
    const transcriptContainer = document.querySelector('.transcript-text');
    if (transcriptContainer) {
        const text = transcriptContainer.textContent;
        const lines = text.split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0);

        // textContent で入れることで、文字起こし中の "<" などを HTML として解釈させない
        transcriptContainer.replaceChildren(...lines.map(line => {
            const p = document.createElement('p');
            p.className = 'transcript-line';
            p.textContent = line;
            return p;
        }));
    }
}

function setupDownloadButton() {
    const downloadButton = document.querySelector('.download-button');
    if (downloadButton) {
        downloadButton.addEventListener('click', function(e) {
            console.log('Starting transcript download');
        });
    }
}