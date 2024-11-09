class RecordingPlayer {
    constructor(recordingData, transcript) {
        this.recordingData = recordingData;
        this.transcript = transcript;
        this.container = document.createElement('div');
        this.container.className = 'recording-player';
        this.isPlaying = false;
        this.audioElement = null;
        this.init();
    }

    init() {
        this.createPlayerStructure();
        this.setupEventListeners();
    }

    createPlayerStructure() {
        const playerWrapper = document.createElement('div');
        playerWrapper.className = 'player-wrapper';

        // オーディオプレーヤーの作成
        this.audioElement = this.createAudioPlayer();
        playerWrapper.appendChild(this.audioElement);

        // コントロールパネルの作成
        const controlPanel = this.createControlPanel();
        playerWrapper.appendChild(controlPanel);

        // プログレスバーの作成
        this.progressBar = this.createProgressBar();
        playerWrapper.appendChild(this.progressBar);

        this.container.appendChild(playerWrapper);

        // メタデータの追加
        this.addMetadata();

        // 文字起こしの追加（存在する場合）
        if (this.transcript) {
            this.addTranscript();
        }
    }

    createAudioPlayer() {
        const audio = document.createElement('audio');
        audio.src = this.recordingData.url;
        audio.preload = 'metadata';
        return audio;
    }

    createControlPanel() {
        const controlPanel = document.createElement('div');
        controlPanel.className = 'control-panel';

        // 再生/一時停止ボタン
        const playButton = document.createElement('button');
        playButton.className = 'play-button';
        playButton.innerHTML = `
            <svg class="play-icon" viewBox="0 0 24 24">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            <svg class="pause-icon hidden" viewBox="0 0 24 24">
                <rect x="6" y="4" width="4" height="16"></rect>
                <rect x="14" y="4" width="4" height="16"></rect>
            </svg>
        `;

        // 時間表示
        const timeDisplay = document.createElement('div');
        timeDisplay.className = 'time-display';
        timeDisplay.textContent = '0:00 / 0:00';

        controlPanel.appendChild(playButton);
        controlPanel.appendChild(timeDisplay);

        this.playButton = playButton;
        this.timeDisplay = timeDisplay;

        return controlPanel;
    }

    createProgressBar() {
        const progressBar = document.createElement('div');
        progressBar.className = 'progress-bar';
        
        const progressFill = document.createElement('div');
        progressFill.className = 'progress-fill';
        progressBar.appendChild(progressFill);

        this.progressFill = progressFill;
        
        return progressBar;
    }

    setupEventListeners() {
        if (this.audioElement) {
            this.playButton.addEventListener('click', () => this.togglePlay());
            this.audioElement.addEventListener('timeupdate', () => this.updateProgress());
            this.audioElement.addEventListener('ended', () => this.handleEnded());
            this.progressBar.addEventListener('click', (e) => this.handleProgressBarClick(e));
        }
    }

    togglePlay() {
        if (!this.audioElement) return;

        if (this.isPlaying) {
            this.audioElement.pause();
        } else {
            this.audioElement.play();
        }
        this.isPlaying = !this.isPlaying;
        this.updatePlayButton();
    }

    updatePlayButton() {
        const playIcon = this.playButton.querySelector('.play-icon');
        const pauseIcon = this.playButton.querySelector('.pause-icon');
        if (this.isPlaying) {
            playIcon.classList.add('hidden');
            pauseIcon.classList.remove('hidden');
        } else {
            playIcon.classList.remove('hidden');
            pauseIcon.classList.add('hidden');
        }
    }

    updateProgress() {
        if (!this.audioElement) return;

        const progress = (this.audioElement.currentTime / this.audioElement.duration) * 100;
        this.progressFill.style.width = `${progress}%`;
        this.updateTimeDisplay();
    }

    updateTimeDisplay() {
        if (!this.audioElement) return;

        const current = this.formatTime(this.audioElement.currentTime);
        const duration = this.formatTime(this.audioElement.duration);
        this.timeDisplay.textContent = `${current} / ${duration}`;
    }

    handleEnded() {
        this.isPlaying = false;
        this.updatePlayButton();
    }

    handleProgressBarClick(event) {
        if (!this.audioElement) return;

        const rect = this.progressBar.getBoundingClientRect();
        const pos = (event.clientX - rect.left) / rect.width;
        this.audioElement.currentTime = pos * this.audioElement.duration;
    }

    formatTime(seconds) {
        if (!seconds || isNaN(seconds)) return '0:00';
        const minutes = Math.floor(seconds / 60);
        seconds = Math.floor(seconds % 60);
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    addMetadata() {
        const metadata = document.createElement('div');
        metadata.className = 'recording-metadata';
        
        const duration = this.recordingData.duration ? 
            this.formatTime(this.recordingData.duration) : '0:00';
        const createdAt = new Date(this.recordingData.created_at).toLocaleString();
        
        metadata.innerHTML = `
            <div class="metadata-item">Duration: ${duration}</div>
            <div class="metadata-item">Created: ${createdAt}</div>
        `;
        
        this.container.appendChild(metadata);
    }

    addTranscript() {
        const transcriptContainer = document.createElement('div');
        transcriptContainer.className = 'transcript-container';
        
        const transcriptTitle = document.createElement('h3');
        transcriptTitle.textContent = 'Transcription';
        transcriptContainer.appendChild(transcriptTitle);

        const transcriptText = document.createElement('div');
        transcriptText.className = 'transcript-text';
        transcriptText.textContent = this.transcript;
        transcriptContainer.appendChild(transcriptText);

        this.container.appendChild(transcriptContainer);
    }
}

// 初期化
document.addEventListener('DOMContentLoaded', () => {
    const playerContainer = document.getElementById('recording-players');
    if (!playerContainer) return;

    try {
        const recordingsData = playerContainer.dataset.recordings;
        const transcript = playerContainer.dataset.transcript;
        
        if (recordingsData) {
            try {
                const recordings = JSON.parse(recordingsData);
                console.log('Parsed recordings:', recordings); // デバッグ用

                if (Array.isArray(recordings)) {
                    // オーディオ録音のみをフィルタリング
                    const audioRecordings = recordings.filter(recording => 
                        recording.type === 'audio'
                    );

                    audioRecordings.forEach(recording => {
                        const player = new RecordingPlayer(recording, transcript);
                        playerContainer.appendChild(player.container);
                    });

                    if (audioRecordings.length === 0) {
                        throw new Error('No audio recordings found');
                    }
                } else {
                    throw new Error('Invalid recordings data format');
                }
            } catch (parseError) {
                console.error('Error parsing recordings data:', parseError);
                throw parseError;
            }
        } else {
            throw new Error('No recordings data found');
        }
    } catch (error) {
        console.error('Error initializing recording players:', error);
        const errorMessage = document.createElement('div');
        errorMessage.className = 'error-message';
        errorMessage.textContent = 'Failed to load audio recordings';
        playerContainer.appendChild(errorMessage);
    }
});