// player.js
class AudioPlayer {
    constructor(compositionSid) {
        this.compositionSid = compositionSid;
        this.audioUrl = null;
        this.duration = 0;
        this.isPlaying = false;
        
        // DOM Elements
        this.audioElement = document.getElementById('audio-player');
        this.playPauseBtn = document.getElementById('playPauseBtn');
        this.playIcon = document.getElementById('playIcon');
        this.pauseIcon = document.getElementById('pauseIcon');
        this.resetBtn = document.getElementById('resetBtn');
        this.downloadBtn = document.getElementById('downloadBtn');
        this.timeDisplay = document.getElementById('timeDisplay');
        this.progressFill = document.getElementById('progressFill');
        
        this.initializeEventListeners();
        this.fetchAudioUrl();
    }
    
    initializeEventListeners() {
        // Play/Pause button
        this.playPauseBtn.addEventListener('click', () => this.handlePlay());
        
        // Reset button
        this.resetBtn.addEventListener('click', () => this.handleReset());
        
        // Download button
        this.downloadBtn.addEventListener('click', () => this.handleDownload());
        
        // Audio element events
        this.audioElement.addEventListener('timeupdate', () => this.handleTimeUpdate());
        this.audioElement.addEventListener('ended', () => this.handleEnded());
    }
    
    async fetchAudioUrl() {
        try {
            const response = await fetch(`/video_chat/compositions/${this.compositionSid}/url/`);
            const data = await response.json();
            
            if (response.ok) {
                this.audioUrl = data.url;
                this.duration = data.duration;
                this.audioElement.src = this.audioUrl;
            } else {
                this.showError(data.error || 'Failed to load audio');
            }
        } catch (err) {
            this.showError('Network error');
        }
    }
    
    handlePlay() {
        if (this.audioElement.paused) {
            this.audioElement.play();
            this.isPlaying = true;
            this.playIcon.classList.add('hidden');
            this.pauseIcon.classList.remove('hidden');
        } else {
            this.audioElement.pause();
            this.isPlaying = false;
            this.playIcon.classList.remove('hidden');
            this.pauseIcon.classList.add('hidden');
        }
    }
    
    handleReset() {
        this.audioElement.currentTime = 0;
        this.updateTimeDisplay();
        this.updateProgressBar();
    }
    
    async handleDownload() {
        if (!this.audioUrl) return;
        
        try {
            const response = await fetch(this.audioUrl);
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `recording-${this.compositionSid}.mp4`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (err) {
            this.showError('Download failed');
        }
    }
    
    handleTimeUpdate() {
        this.updateTimeDisplay();
        this.updateProgressBar();
    }
    
    handleEnded() {
        this.isPlaying = false;
        this.playIcon.classList.remove('hidden');
        this.pauseIcon.classList.add('hidden');
    }
    
    updateTimeDisplay() {
        const currentTime = this.audioElement.currentTime;
        const duration = this.audioElement.duration || this.duration;
        this.timeDisplay.textContent = `${this.formatTime(currentTime)} / ${this.formatTime(duration)}`;
    }
    
    updateProgressBar() {
        const progress = (this.audioElement.currentTime / (this.audioElement.duration || this.duration)) * 100;
        this.progressFill.style.width = `${progress}%`;
    }
    
    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
    
    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = `Error: ${message}`;
        
        const player = document.querySelector('.audio-player');
        player.innerHTML = '';
        player.appendChild(errorDiv);
    }
}

// Initialize the player when the page loads
document.addEventListener('DOMContentLoaded', () => {
    // Get the composition SID from wherever it's stored (e.g., data attribute)
    const compositionSid = document.querySelector('.audio-player').dataset.compositionSid;
    new AudioPlayer(compositionSid);
});