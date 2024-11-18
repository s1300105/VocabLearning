class RecordingPlayer {
    constructor(recordingData) {
        console.log('Constructor: Starting initialization');
        this.recordingData = recordingData;
        this.container = document.createElement('div');
        this.container.className = 'recording-player';
        this.isPlaying = false;
        
        // UI要素の参照を初期化
        this.audioElement = null;
        this.playButton = null;
        this.timeDisplay = null;
        this.progressBar = null;
        this.progressFill = null;
        
        // 初期化を実行
        this.init();
    }

    init() {
        console.log('Init: Creating audio element');
        this.audioElement = document.createElement('audio');
        this.audioElement.src = this.recordingData.url;
        this.audioElement.preload = 'metadata';

        // オーディオ要素のロードを待ってからUIを作成
        this.audioElement.addEventListener('loadedmetadata', () => {
            console.log('Audio metadata loaded');
            this.createPlayerUI();
            this.attachEventListeners();
        });

        // エラーハンドリング
        this.audioElement.addEventListener('error', (e) => {
            console.error('Audio element error:', e);
        });
    }

    createPlayerUI() {
        console.log('Creating UI elements');
        try {
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
            this.progressBar = document.createElement('div');
            this.progressBar.className = 'progress-bar';
            this.progressFill = document.createElement('div');
            this.progressFill.className = 'progress-fill';
            this.progressBar.appendChild(this.progressFill);
        
            // 要素を追加
            controlPanel.appendChild(this.playButton);
            controlPanel.appendChild(this.timeDisplay);
            this.container.appendChild(controlPanel);
            this.container.appendChild(this.progressBar);

            console.log('UI elements created successfully');
        } catch (error) {
            console.error('Error creating UI:', error);
        }
    }

    attachEventListeners() {
        console.log('Attaching event listeners');
        try {
            // 要素の存在確認
            if (!this.playButton) {
                throw new Error('Play button not found');
            }
            if (!this.audioElement) {
                throw new Error('Audio element not found');
            }
            if (!this.progressBar) {
                throw new Error('Progress bar not found');
            }

            // イベントリスナーを設定
            const boundTogglePlay = this.togglePlay.bind(this);
            const boundUpdateProgress = this.updateProgress.bind(this);
            const boundHandleEnded = this.handleEnded.bind(this);
            const boundHandleProgressBarClick = this.handleProgressBarClick.bind(this);

            this.playButton.addEventListener('click', boundTogglePlay);
            this.audioElement.addEventListener('timeupdate', boundUpdateProgress);
            this.audioElement.addEventListener('ended', boundHandleEnded);
            this.progressBar.addEventListener('click', boundHandleProgressBarClick);

            console.log('Event listeners attached successfully');
        } catch (error) {
            console.error('Error attaching event listeners:', error);
            throw error;
        }
    }

    togglePlay() {
        if (!this.audioElement) return;
        
        if (this.isPlaying) {
            this.audioElement.pause();
        } else {
            this.audioElement.play().catch(error => {
                console.error('Error playing audio:', error);
            });
        }
        this.isPlaying = !this.isPlaying;
        this.updatePlayButton();
    }

    updatePlayButton() {
        if (!this.playButton) return;
        
        const playIcon = this.playButton.querySelector('.play-icon');
        const pauseIcon = this.playButton.querySelector('.pause-icon');
        
        if (this.isPlaying) {
            playIcon?.classList.add('hidden');
            pauseIcon?.classList.remove('hidden');
        } else {
            playIcon?.classList.remove('hidden');
            pauseIcon?.classList.add('hidden');
        }
    }

    updateProgress() {
        if (!this.audioElement || !this.progressFill) return;
        
        const progress = (this.audioElement.currentTime / this.audioElement.duration) * 100;
        this.progressFill.style.width = `${progress}%`;
        this.updateTimeDisplay();
    }

    updateTimeDisplay() {
        if (!this.timeDisplay || !this.audioElement) return;
        
        const current = this.formatTime(this.audioElement.currentTime);
        const duration = this.formatTime(this.audioElement.duration);
        this.timeDisplay.textContent = `${current} / ${duration}`;
    }

    handleEnded() {
        this.isPlaying = false;
        this.updatePlayButton();
    }

    handleProgressBarClick(event) {
        if (!this.audioElement || !this.progressBar) return;
        
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
}

// 初期化コード
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded');
    
    const playerContainer = document.getElementById('recording-players');
    const playerWrapper = document.querySelector('.player-wrapper');

    if (!playerContainer) {
        console.error('Player container not found');
        return;
    }
    if (!playerWrapper) {
        console.error('Player wrapper not found');
        return;
    }

    try {
        const recordingsData = playerContainer.dataset.recordings;
        if (!recordingsData) {
            throw new Error('No recordings data found');
        }

        const recordings = JSON.parse(recordingsData);
        console.log('Parsed recordings:', recordings);

        // 既存のプレーヤーをクリア
        playerWrapper.innerHTML = '';

        if (Array.isArray(recordings)) {
            const audioRecordings = recordings.filter(recording => recording.type === 'audio');
            if (audioRecordings.length === 0) {
                throw new Error('No audio recordings found');
            }

            audioRecordings.forEach(recording => {
                console.log('Creating player for recording:', recording);
                const player = new RecordingPlayer(recording);
                playerWrapper.appendChild(player.container);
            });
        } else if (recordings.type === 'audio') {
            console.log('Creating single player');
            const player = new RecordingPlayer(recordings);
            playerWrapper.appendChild(player.container);
        } else {
            throw new Error('Invalid recording data format');
        }
    } catch (error) {
        console.error('Error initializing recording players:', error);
        const errorMessage = document.createElement('div');
        errorMessage.className = 'error-message';
        errorMessage.textContent = 'Failed to load audio recordings';
        playerContainer.appendChild(errorMessage);
    }
});