class CompositionStatusChecker {
    constructor(compositionSid) {
        this.compositionSid = compositionSid;
        this.checkInterval = null;
        this.container = document.getElementById('status-checker');
        this.initializeChecker();
    }

    async checkStatus() {
        try {
            const response = await fetch(`/video_chat/api/compositions/${this.compositionSid}/status`);
            const data = await response.json();
            
            if (data.status === 'completed') {
                window.location.href = `/video_chat/player/${this.compositionSid}/`;
            } else if (data.status === 'failed') {
                this.showError('Processing failed. Please try again.');
                this.stopChecking();
            } else {
                this.updateStatus(data.status);
            }
        } catch (err) {
            this.showError('Failed to check status. Please refresh the page.');
            this.stopChecking();
        }
    }

    initializeChecker() {
        this.checkInterval = setInterval(() => this.checkStatus(), 3000);
        this.renderInitialState();
    }

    stopChecking() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
        }
    }

    renderInitialState() {
        this.container.innerHTML = `
            <div class="processing-container">
                <div class="processing-content">
                    <div class="spinner"></div>
                    <h2 class="processing-title">Processing Recording</h2>
                    <p class="processing-message">
                        Please wait while we process your recording...
                    </p>
                </div>
            </div>
        `;
    }

    updateStatus(status) {
        const messageElement = this.container.querySelector('.processing-message');
        if (messageElement) {
            messageElement.textContent = `Current status: ${status}`;
        }
    }

    showError(message) {
        this.container.innerHTML = `
            <div class="processing-container error">
                <div class="processing-content">
                    <div class="error-icon">⚠️</div>
                    <h2 class="processing-title">Error</h2>
                    <p class="processing-message error-message">${message}</p>
                    <button onclick="window.location.reload()" class="retry-button">
                        Retry
                    </button>
                </div>
            </div>
        `;
    }
}

// Initialize when the page loads
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('status-checker');
    const compositionSid = container.dataset.compositionSid;
    new CompositionStatusChecker(compositionSid);
});