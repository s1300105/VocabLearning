// static/video_chat/js/video.js を更新

let room = null;
let joinButton;
let leaveButton;


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
        
        if (data.status === "success") {
            // room_sidを含めてプレーヤーページにリダイレクト
            window.location.href = `/video_chat/player/?room_sid=${roomSid}`;
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
        log(`Leaving room to transcribe with SID ${roomSid}`);
        showLoading();

        // 部屋から退出
        log('Disconnecting room...');
        room.disconnect();
        room = null;


        await new Promise(resolve => setTimeout(resolve, 5000)); // 5秒待機

        // 録画完了を通知
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

        if (data.status === "success") {
            // 文字起こし処理のリクエスト
            const transcribeResponse = await fetch('/video_chat/go_transcribe/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    RoomSid: roomSid
                })
            });

            if (!transcribeResponse.ok) {
                throw new Error('Failed to transcribe audio');
            }

            const transcribeData = await transcribeResponse.json();

            if (transcribeData.status === 'success') {
                hideLoading();
                // URLエンコードを使用して文字起こしデータを安全に渡す
                const encodedTranscript = encodeURIComponent(transcribeData.transcript);
                window.location.href = `/video_chat/player/?room_sid=${roomSid}&transcript=${encodedTranscript}`;
            } else {
                throw new Error('Transcription failed');
            }
        } else {
            throw new Error('Recording completion failed');
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




// DOMContentLoaded イベントリスナー
document.addEventListener('DOMContentLoaded', function() {
    log('Initializing video chat controls...');
    
    joinButton = document.getElementById('join-button');
    leaveButton = document.getElementById('leave-button');
    
    if (joinButton) {
        log('Join button found');
    } else {
        log('Warning: Join button not found');
    }
    
    if (leaveButton) {
        log('Leave button found');
        leaveButton.addEventListener('click', leaveRoom);
    } else {
        log('Warning: Leave button not found');
    }
});





// joinRoom関数を修正
async function joinRoom() {
    const roomName = document.getElementById('room-name').value;
    const userType = document.getElementById('user-type').value; // HTMLに追加必要

    
    
    if (!roomName) {
        alert('Please enter a room name');
        return;
    }

    if (!userType) {
        alert('Please select user type');
        return;
    }

    joinButton.disabled = true;
    log(`Attempting to join room: ${roomName} as ${userType}`);

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






