// static/video_chat/js/video.js を更新

let room = null;
let joinButton;
let leaveButton;

document.addEventListener('DOMContentLoaded', function() {
    joinButton = document.getElementById('join-button');
    leaveButton = document.getElementById('leave-button');
});

function log(message) {
    console.log(message);
    const debugLog = document.getElementById('debug-log');
    const time = new Date().toISOString();
    debugLog.innerHTML += `<div>${time}: ${message}</div>`;
    debugLog.scrollTop = debugLog.scrollHeight;
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

// 部屋を退出する関数を追加
// video.js の leaveRoom 関数を修正
async function leaveRoom() {
    if (room) {
        try {
            const roomSid = room.sid;
            log(`Leaving room with SID: ${roomSid}`);
            
            // 部屋を切断
            room.disconnect();
            room = null;
            
            // 録音完了を通知
            const response = await fetch('/video_chat/recording-complete/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    RoomSid: roomSid
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.redirect_url) {
                    // 処理完了を待ってからリダイレクト
                    window.location.href = data.redirect_url;
                    return;
                }
            }
            
        } catch (error) {
            log(`Error in leaveRoom: ${error.message}`);
            alert('Failed to complete recording process');
        }
        
        // エラー時のフォールバック
        document.getElementById('video-container').innerHTML = '';
        joinButton.style.display = 'inline-block';
        leaveButton.style.display = 'none';
        joinButton.disabled = false;
    }
}

// 既存のjoinRoom関数
async function joinRoom() {
    const roomName = document.getElementById('room-name').value;
    if (!roomName) {
        alert('Please enter a room name');
        return;
    }

    joinButton.disabled = true;
    log(`Attempting to join room: ${roomName}`);

    try {
        const response = await fetch('/video_chat/make_token/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ room_name: roomName })
        });

        log(`Response status: ${response.status}`);
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        log('Connecting to Twilio room...');
        room = await Twilio.Video.connect(data.token, {
            name: roomName,
            audio: true,
            video: { width: 640, height: 480 }
        });

        log('Successfully connected to room');
        handleRoomConnection(room);

        joinButton.style.display = 'none';
        leaveButton.style.display = 'inline-block';

    } catch (error) {
        log(`Error: ${error.message}`);
        alert(`Failed to join room: ${error.message}`);
        joinButton.disabled = false;
    }
}

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

// CSRFトークンを取得する関数
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