class CompositionStatusChecker {
    constructor(compositionSid) {
        this.compositionSid = compositionSid;
        this.checkInterval = null;
    }

    startChecking() {
        // 5秒ごとにステータスをチェック
        this.checkInterval = setInterval(() => this.checkStatus(), 5000);
        // 初回チェック
        this.checkStatus();
    }

    async checkStatus() {
        try {
            const response = await fetch(`/video_chat/api/compositions/${this.compositionSid}/status/`);
            const data = await response.json();

            if (data.status === 'completed') {
                // 完了したら画面をリロード
                window.location.reload();
                this.stopChecking();
            } else if (data.status === 'failed') {
                // エラーの場合もチェックを停止
                this.showError(data.message || 'Processing failed');
                this.stopChecking();
            }
        } catch (error) {
            console.error('Error checking status:', error);
        }
    }

    stopChecking() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
        }
    }

    showError(message) {
        const processingMessage = document.querySelector('.processing-message');
        if (processingMessage) {
            processingMessage.innerHTML = `<p class="error">${message}</p>`;
        }
    }
}