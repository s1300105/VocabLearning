document.addEventListener('DOMContentLoaded', function() {
    // 定数定義
    const API_ENDPOINTS = {
        RECORDING_COMPLETE: '/video_chat/recording-complete/',
    };

    // メイン関数
    async function initializeAnalysis() {
        const urlParams = new URLSearchParams(window.location.search);
        const roomSid = urlParams.get('room_sid');
        
        if (roomSid) {
            await fetchAndDisplayAnalysis(roomSid);
        }
    }

    // 分析データの取得と表示
    async function fetchAndDisplayAnalysis(roomSid) {
        try {
            showLoading(true);
            
            const response = await fetch(API_ENDPOINTS.RECORDING_COMPLETE, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ RoomSid: roomSid })
            });
            
            if (!response.ok) {
                throw new Error('Failed to fetch analysis data');
            }
            
            const data = await response.json();
            displayAnalysisResults(data);
            
        } catch (error) {
            showError(error.message);
        } finally {
            showLoading(false);
        }
    }

    // 文字起こしの表示
    function displayTranscripts(transcripts) {
        const teacherTranscript = document.getElementById('teacher-transcript');
        const studentTranscript = document.getElementById('student-transcript');
        
        transcripts.forEach(transcript => {
            const element = document.createElement('div');
            element.className = 'transcript-entry';
            element.textContent = transcript.text;
            
            if (transcript.speaker === 'teacher') {
                teacherTranscript.appendChild(element);
            } else {
                studentTranscript.appendChild(element);
            }
        });
    }

    // 音声プレイヤーの作成
    function createAudioPlayers(audioUrls) {
        const container = document.getElementById('audio-players');
        container.innerHTML = '';
        
        audioUrls.forEach((url, index) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'audio-player-wrapper';
            
            const audio = document.createElement('audio');
            audio.controls = true;
            audio.src = url;
            
            const label = document.createElement('div');
            label.className = 'audio-label';
            label.textContent = `Recording ${index + 1}`;
            
            wrapper.appendChild(label);
            wrapper.appendChild(audio);
            container.appendChild(wrapper);
        });
    }

    // メトリクスの更新
    function updateMetrics(data) {
        document.getElementById('speaking-time').textContent = formatTime(data.total_speaking_time);
        document.getElementById('word-count').textContent = data.total_words;
        document.getElementById('vocabulary-score').textContent = data.vocabulary_score;
        document.getElementById('grammar-score').textContent = data.grammar_score;
    }

    // 詳細な分析の表示
    function displayDetailedAnalysis(data) {
        // Plotly.jsを使用してグラフを作成
        const chartData = [{
            values: [data.student_speaking_time, data.teacher_speaking_time],
            labels: ['Student', 'Teacher'],
            type: 'pie'
        }];
        
        Plotly.newPlot('analysis-charts', chartData);
    }

    // 会話タイムラインの表示
    function displayConversationTimeline(data) {
        const timeline = document.getElementById('conversation-timeline');
        timeline.innerHTML = '';
        
        data.conversation_flow.forEach(item => {
            const element = document.createElement('div');
            element.className = 'conversation-item';
            
            element.innerHTML = `
                <div class="speaker-label">${item.speaker}:</div>
                <div class="speech-content">${item.text}</div>
            `;
            
            timeline.appendChild(element);
        });
    }

    // ユーティリティ関数
    function showLoading(show) {
        document.getElementById('loading').classList.toggle('active', show);
    }

    function showError(message) {
        const errorElement = document.getElementById('error-message');
        errorElement.textContent = message;
        errorElement.style.display = 'block';
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

    function formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }

    // 初期化
    initializeAnalysis();
});