// グローバル変数の定義
let room = null;
let joinButton;
let leaveButton;
let currentUserType = null;
let connectionAttempts = 0;
const MAX_RETRY_ATTEMPTS = 3;
let isConnecting = false;

// 接続状態を管理するクラス
class ConnectionManager {
    constructor() {
        this.isConnecting = false;
        this.currentRoom = null;
        this.reconnectTimeout = null;
    }

    async connect(token, roomName, options = {}) {
        if (this.isConnecting) {
            log('Connection already in progress');
            return null;
        }

        try {
            this.isConnecting = true;
            log('Initiating connection to room: ' + roomName);

            const connectOptions = {
                name: roomName,
                audio: true,
                video: { width: 640, height: 480 },
                networkQuality: {
                    local: 1,
                    remote: 1
                },
                dominantSpeaker: true,
                maxAudioBitrate: 16000,
                preferredVideoCodecs: [{ codec: 'VP8', simulcast: true }],
                ...options
            };

            const room = await Twilio.Video.connect(token, connectOptions);
            this.currentRoom = room;
            
            // 接続状態の監視を設定
            this.setupConnectionMonitoring(room);
            
            return room;
        } catch (error) {
            log('Connection error: ' + error.message);
            throw error;
        } finally {
            this.isConnecting = false;
        }
    }

    setupConnectionMonitoring(room) {
        room.on('disconnected', (room, error) => {
            log('Disconnected from room:', error ? error.message : 'No error');
            this.handleDisconnection(error);
        });

        room.on('reconnecting', error => {
            log('Reconnecting to room:', error ? error.message : 'No error');
        });

        room.on('reconnected', () => {
            log('Successfully reconnected to room');
        });

        // ネットワーク品質の監視
        room.localParticipant.on('networkQualityLevelChanged', level => {
            log(`Network quality changed to level: ${level}`);
        });
    }

    handleDisconnection(error) {
        if (this.currentRoom) {
            this.currentRoom = null;
            updateUIForDisconnection();
            
            if (error && connectionAttempts < MAX_RETRY_ATTEMPTS) {
                const delay = Math.min(1000 * Math.pow(2, connectionAttempts), 10000);
                connectionAttempts++;
                setTimeout(() => this.retryConnection(), delay);
            }
        }
    }

    async retryConnection() {
        if (this.isConnecting || this.currentRoom) return;

        try {
            const response = await getNewToken();
            if (response.token) {
                await this.connect(response.token, response.roomName);
                connectionAttempts = 0;
            }
        } catch (error) {
            log('Retry connection failed: ' + error.message);
        }
    }

    disconnect() {
        if (this.currentRoom) {
            this.currentRoom.disconnect();
            this.currentRoom = null;
        }
        connectionAttempts = 0;
        updateUIForDisconnection();
    }
}

const connectionManager = new ConnectionManager();


function log(message) {
    console.log(message);
    const debugLog = document.getElementById('debug-log');
    if (debugLog) {
        const time = new Date().toISOString();
        debugLog.innerHTML += `<div>${time}: ${message}</div>`;
        debugLog.scrollTop = debugLog.scrollHeight;
    }
}




// 参加者のコンテナを作成する関数を追加
function createParticipantContainer(participant) {
    const container = document.createElement('div');
    container.className = 'participant';
    container.id = participant.identity;

    const title = document.createElement('div');
    title.className = 'participant-title';
    title.innerText = participant.identity;
    container.appendChild(title);

    document.getElementById('video-container').appendChild(container);
    return container;
}

// リモート参加者を処理する関数を追加
function handleRemoteParticipant(participant) {
    log(`Remote participant ${participant.identity} connected`);
    const container = createParticipantContainer(participant);

    participant.tracks.forEach(publication => {
        if (publication.track) {
            container.appendChild(publication.track.attach());
        }
    });

    participant.on('trackSubscribed', track => {
        log(`Subscribed to ${track.kind} track from ${participant.identity}`);
        container.appendChild(track.attach());
    });

    participant.on('trackUnsubscribed', track => {
        log(`Unsubscribed from ${track.kind} track from ${participant.identity}`);
        track.detach().forEach(element => element.remove());
    });
}

// 参加者の切断を処理する関数を追加
function handleParticipantDisconnected(participant) {
    log(`Participant ${participant.identity} disconnected`);
    document.getElementById(participant.identity).remove();
}


async function leaveRoom() {
    if (!room) {
        log('No active room to leave');
        return;
    }

    try {
        const roomSid = room.sid;
        log(`Leaving room with SID: ${roomSid}`);
        
        // 部屋を切断
        log('Disconnecting room...');
        room.disconnect();
        room = null;

        // 録音完了エンドポイントを呼び出し
        const response = await fetch('/video_chat/recording-complete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                RoomSid: roomSid
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        transcript = data.transcript;
        
        if (data.status === "success") {
            // room_sidを含めてプレーヤーページにリダイレクト
            window.location.href = `/video_chat/player/?room_sid=${roomSid}&transcript=${transcript}`;
        } else {
            log(`Error: ${data.error || 'Unknown error'}`);
            showError('Failed to process recording');
        }
        
    } catch (error) {
        log(`Error in leaveRoom: ${error.message}`);
        console.error('Detailed error:', error);
        showError('Failed to leave room');
    }
}



/*
async function leaveRoom2() {
    if (!room) {
        log('No active room to leave');
        return;
    }

    try {
        const roomSid = room.sid;
        log(`Leaving room to transcribe with SID ${roomSid}`);
        showLoading();

        // 部屋から退出
        log('Disconnecting room...');
        room.disconnect();
        room = null;

        // 録画処理が完了するまで待機
        await new Promise(resolve => setTimeout(resolve, 2000));

        // 文字起こし処理のリクエスト
        const response = await fetch('/video_chat/go_transcribe/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                RoomSid: roomSid
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }

        if (data.status === 'success') {
            log('Transcription completed successfully');
            hideLoading();
            window.location.href = `/video_chat/transcribe_audio/?sid=${data.sid}`;
        } else {
            throw new Error('Transcription failed');
        }

    } catch (error) {
        hideLoading();
        log(`Error in leaveRoom2: ${error.message}`);
        console.error('Detailed error:', error);
        alert(`Failed to process transcription: ${error.message}`);
    }
}

*/



async function leaveRoom2() {
    if (!room) {
        log('No active room to leave');
        return;
    }

    try {
        const roomSid = room.sid;
        const maxRetries = 3;
        let attempt = 0;

        log(`Leaving room to transcribe with SID ${roomSid}`);

        // teacherの場合は直接video_lessonページに戻る
        if (currentUserType === 'teacher') {
            log('Teacher detected, redirecting to video lesson page');
            room.disconnect();
            room = null;
            window.location.href = '/video_chat/video_lesson/';
            return;
        }

        showLoading();
        log('Student detected, processing recording and transcription');

        // 部屋から退出
        log('Disconnecting room...');
        room.disconnect();
        room = null;

        // 録音の完了を待つ
        log('Waiting for recording to complete...');
        await new Promise(resolve => setTimeout(resolve, 15000));

        while (attempt < maxRetries) {
            try {
                log(`Attempting to fetch recording (attempt ${attempt + 1}/${maxRetries})`);
                const response = await fetch('/video_chat/recording-complete/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                    body: JSON.stringify({
                        RoomSid: roomSid,
                        transcribe: true
                    })
                });

                const data = await response.json();

                if (response.status === 202) {
                    // まだ録音が準備できていない場合
                    log("Recording not ready yet, retrying...");
                    await new Promise(resolve => setTimeout(resolve, 5000));
                    attempt++;
                    continue;
                }

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}, message: ${data.error || 'Unknown error'}`);
                }

                if (data.status === "success") {
                    hideLoading();
                    log('Recording and transcription successful');
                    if (data.transcript) {
                        const encodedTranscript = encodeURIComponent(data.transcript);
                        window.location.href = `/video_chat/player/?room_sid=${roomSid}&transcript=${encodedTranscript}`;
                    } else {
                        throw new Error('No transcript received');
                    }
                    return;
                }

                throw new Error(data.error || 'Recording completion failed');

            } catch (error) {
                log(`Error on attempt ${attempt + 1}: ${error.message}`);
                
                if (attempt === maxRetries - 1) {
                    hideLoading();
                    throw new Error(`Failed after ${maxRetries} attempts: ${error.message}`);
                }
                
                attempt++;
                await new Promise(resolve => setTimeout(resolve, 5000));
            }
        }

    } catch (error) {
        hideLoading();
        log(`Error in leaveRoom2: ${error.message}`);
        console.error('Detailed error:', error);
        alert(`Failed to process recording and transcription: ${error.message}`);
    }
}







// ユーティリティ関数
function showLoading() {
    const loading = document.querySelector('.loading');
    if (loading) loading.style.display = 'block';
}

function hideLoading() {
    const loading = document.querySelector('.loading');
    if (loading) loading.style.display = 'none';
}



async function joinRoom() {
    if (connectionManager.isConnecting) {
        alert('Connection already in progress');
        return;
    }

    const roomName = document.getElementById('room-name').value;
    const userType = document.getElementById('user-type').value;

    if (!roomName || !userType) {
        alert('Please enter room name and select user type');
        return;
    }

    currentUserType = userType;
    joinButton.disabled = true;

    try {
        const response = await fetch('/video_chat/make_token/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ 
                room_name: roomName,
                user_type: userType
            })
        });

        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }

        room = await connectionManager.connect(data.token, roomName);
        
        if (room) {
            handleRoomConnection(room);
            joinButton.style.display = 'none';
            leaveButton.style.display = 'inline-block';
        }

    } catch (error) {
        log(`Error: ${error.message}`);
        alert(`Failed to join room: ${error.message}`);
        joinButton.disabled = false;
    }
}

function updateUIForDisconnection() {
    joinButton.style.display = 'inline-block';
    joinButton.disabled = false;
    leaveButton.style.display = 'none';
}

// イベントリスナーの設定
document.addEventListener('DOMContentLoaded', function() {
    log('Initializing video chat controls...');
    
    joinButton = document.getElementById('join-button');
    leaveButton = document.getElementById('leave-button');
    
    const userTypeSelect = document.getElementById('user-type');
    if (userTypeSelect) {
        userTypeSelect.addEventListener('change', function(e) {
            currentUserType = e.target.value;
            log(`User type changed to: ${currentUserType}`);
        });
    }
    
    if (joinButton) {
        log('Join button found');
        joinButton.addEventListener('click', joinRoom);
    }
    
    if (leaveButton) {
        log('Leave button found');
        leaveButton.addEventListener('click', () => {
            connectionManager.disconnect();
            if (currentUserType === 'student') {
                handleStudentLeave();
            } else {
                handleTeacherLeave();
            }
        });
    }
});



// ルーム接続を処理する関数
function handleRoomConnection(room) {
    handleLocalParticipant(room.localParticipant);
    room.participants.forEach(handleRemoteParticipant);
    room.on('participantConnected', handleRemoteParticipant);
    room.on('participantDisconnected', handleParticipantDisconnected);
}

// ローカル参加者を処理する関数
function handleLocalParticipant(participant) {
    log(`Setting up local participant: ${participant.identity}`);
    const container = createParticipantContainer(participant);
    
    participant.tracks.forEach(publication => {
        if (publication.track) {
            container.appendChild(publication.track.attach());
        }
    });
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}


async function handleRecordingComplete(roomSid) {
    try {
        const response = await fetch('/video_chat/recording-complete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ RoomSid: roomSid })
        });
        
        const data = await response.json();
        if (data.transcripts) {
            // 文字起こしと分析結果を表示
            displayAnalysis(data.transcripts);
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function displayAnalysis(transcripts) {
    const container = document.getElementById('analysis-container');
    transcripts.forEach(transcript => {
        const div = document.createElement('div');
        div.innerHTML = `
            <h3>Speech Analysis</h3>
            <p><strong>Transcript:</strong> ${transcript.text}</p>
            <p><strong>Word Count:</strong> ${transcript.word_count}</p>
            <p><strong>Sentiment:</strong> ${transcript.sentiment}</p>
            <div class="grammar-errors">
                <h4>Grammar Issues:</h4>
                <ul>
                    ${transcript.grammar_errors.map(error => `<li>${error}</li>`).join('')}
                </ul>
            </div>
        `;
        container.appendChild(div);
    });
}






