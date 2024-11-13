class RecordingPlayer {
    constructor(recordingData) {
        console.log('Creating player with data:', recordingData);
        this.recordingData = recordingData;
        //this.transcript = transcript;
        this.container = document.createElement('div');
        this.container.className = 'recording-player';
        this.isPlaying = false;
        this.audioElement = null;
        this.init();
    }

    init(recordingData) {
        // オーディオ要素の作成と設定
        this.audioElement = document.createElement('audio');
        this.audioElement.src = this.recordingData.url;
        this.audioElement.preload = 'metadata';

        // プレーヤーのUIを作成
        this.createPlayerUI();
        this.setupEventListeners();
    }


    createPlayerUI() {
        // オーディオ要素を追加
        this.container.appendChild(this.audioElement);
    
        // プレーヤーコントロール
        const controlPanel = document.createElement('div');
        controlPanel.className = 'control-panel';
    
        // 再生/一時停止ボタン
        this.playButton = document.createElement('button');
        this.playButton.className = 'play-button';
        this.playButton.innerHTML = `
            <svg class="play-icon" viewBox="0 0 24 24">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            <svg class="pause-icon hidden" viewBox="0 0 24 24">
                <rect x="6" y="4" width="4" height="16"></rect>
                <rect x="14" y="4" width="4" height="16"></rect>
            </svg>
        `;
    
        // 時間表示
        this.timeDisplay = document.createElement('div');
        this.timeDisplay.className = 'time-display';
        this.timeDisplay.textContent = '0:00 / 0:00';
    
        // プログレスバー
        const progressBar = document.createElement('div');
        progressBar.className = 'progress-bar';
        this.progressFill = document.createElement('div');
        this.progressFill.className = 'progress-fill';
        progressBar.appendChild(this.progressFill);
    
        // 要素を追加
        controlPanel.appendChild(this.playButton);
        controlPanel.appendChild(this.timeDisplay);
        this.container.appendChild(controlPanel);
        this.container.appendChild(progressBar);
    }


    setupEventListeners() {
        this.playButton.addEventListener('click', () => this.togglePlay());
        this.audioElement.addEventListener('timeupdate', () => this.updateProgress());
        this.audioElement.addEventListener('ended', () => this.handleEnded());
        document.querySelector('.progress-bar').addEventListener('click', (e) => this.handleProgressBarClick(e));
    }

    togglePlay() {
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
        const progress = (this.audioElement.currentTime / this.audioElement.duration) * 100;
        this.progressFill.style.width = `${progress}%`;
        this.updateTimeDisplay();
    }

    updateTimeDisplay() {
        const current = this.formatTime(this.audioElement.currentTime);
        const duration = this.formatTime(this.audioElement.duration);
        this.timeDisplay.textContent = `${current} / ${duration}`;
    }

    handleEnded() {
        this.isPlaying = false;
        this.updatePlayButton();
    }

    handleProgressBarClick(event) {
        const progressBar = event.currentTarget;
        const rect = progressBar.getBoundingClientRect();
        const pos = (event.clientX - rect.left) / rect.width;
        this.audioElement.currentTime = pos * this.audioElement.duration;
    }

    formatTime(seconds) {
        if (!seconds || isNaN(seconds)) return '0:00';
        const minutes = Math.floor(seconds / 60);
        seconds = Math.floor(seconds % 60);
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }
}


// 初期化コード
document.addEventListener('DOMContentLoaded', () => {
    const playerContainer = document.getElementById('recording-players');
    if (!playerContainer) return;

    try {
        const recordingsData = playerContainer.dataset.recordings;
        // transcriptはJavaScriptでは使用しない
        
        if (recordingsData) {
            try {
                const recordings = JSON.parse(recordingsData);
                console.log('Parsed recordings:', recordings);

                if (Array.isArray(recordings)) {
                    const audioRecordings = recordings.filter(recording => 
                        recording.type === 'audio'
                    );

                    audioRecordings.forEach(recording => {
                        const player = new RecordingPlayer(recording);  // transcriptを渡さない
                        const playerWrapper = document.querySelector('.player-wrapper');
                        if (playerWrapper) {
                            playerWrapper.innerHTML = '';
                            playerWrapper.appendChild(player.container);
                        }
                    });

                    if (audioRecordings.length === 0) {
                        throw new Error('No audio recordings found');
                    }
                } else {
                    if (recordings.type === 'audio') {
                        const player = new RecordingPlayer(recordings);  // transcriptを渡さない
                        const playerWrapper = document.querySelector('.player-wrapper');
                        if (playerWrapper) {
                            playerWrapper.innerHTML = '';
                            playerWrapper.appendChild(player.container);
                        }
                    } else {
                        throw new Error('Invalid recording data format');
                    }
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