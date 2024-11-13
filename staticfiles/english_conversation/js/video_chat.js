
// 既存のコードに追加
class AudioProcessor {
    constructor() {
        this.ws = null;
        this.processing = false;
    }

    connect(url) {
        this.ws = new WebSocket(url);
        this.ws.onmessage = this.handleMessage.bind(this);
    }

    handleMessage(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'ai_feedback') {
            this.updateFeedback(data.data);
        }
    }

    updateFeedback(feedback) {
        // 文字起こしの表示
        if (feedback.transcription) {
            const transcriptionDiv = document.getElementById('transcription-content');
            transcriptionDiv.innerHTML += `
                <p>${feedback.transcription}</p>
            `;
            transcriptionDiv.scrollTop = transcriptionDiv.scrollHeight;
        }

        // 文法訂正の表示
        if (feedback.corrections && feedback.corrections.length > 0) {
            const correctionDiv = document.getElementById('correction-content');
            feedback.corrections.forEach(correction => {
                correctionDiv.innerHTML += `
                    <div class="correction">
                        <span class="original">${correction.original}</span> →
                        <span class="corrected">${correction.corrected}</span>
                    </div>
                `;
            });
            correctionDiv.scrollTop = correctionDiv.scrollHeight;
        }

        // フレーズ提案の表示
        if (feedback.suggestions && feedback.suggestions.length > 0) {
            const suggestionDiv = document.getElementById('suggestion-content');
            feedback.suggestions.forEach(suggestion => {
                suggestionDiv.innerHTML += `
                    <div class="suggestion-pill" onclick="useSuggestion(this)">
                        ${suggestion}
                    </div>
                `;
            });
        }
    }

    processAudio(audioData) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'audio',
                audio: audioData
            }));
        }
    }
}

// 既存のjoinRoom関数を修正
async function joinRoom() {
    const roomName = document.getElementById('room-name').value;
    if (!roomName) {
        alert('Please enter a room name');
        return;
    }

    try {
        const response = await fetch('/english_conversation/generate_token/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ room_name: roomName })
        });

        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }

        // AudioProcessorの初期化と接続
        const audioProcessor = new AudioProcessor();
        audioProcessor.connect(data.ws_url);

        // Twilioルームへの接続
        room = await Twilio.Video.connect(data.token, {
            name: roomName,
            audio: true,
            video: { width: 640, height: 480 }
        });

        // 音声処理の設定
        room.localParticipant.audioTracks.forEach(publication => {
            const track = publication.track;
            track.on('sample', (sample) => {
                audioProcessor.processAudio(sample.data);
            });
        });

        // UI更新
        handleRoomConnection(room);
        document.getElementById('join-button').style.display = 'none';
        document.getElementById('leave-button').style.display = 'inline-block';
        document.querySelector('.media-controls').style.display = 'block';
        document.getElementById('room-name').disabled = true;

    } catch (error) {
        console.error('Error:', error);
        alert(`Failed to join room: ${error.message}`);
        document.getElementById('join-button').disabled = false;
    }
}

// 提案されたフレーズを使用する関数
function useSuggestion(element) {
    const text = element.textContent.trim();
    // クリップボードにコピー
    navigator.clipboard.writeText(text).then(() => {
        alert('Phrase copied to clipboard!');
    });
}
