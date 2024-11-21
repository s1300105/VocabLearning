document.addEventListener('DOMContentLoaded', function() {
    const modelAudio = document.getElementById('model-audio');
    const learnerAudio = document.getElementById('learner-audio');
    const sentenceAudio = document.getElementById('sentence-audio');
    const message = document.getElementById('message');
    const pronunciationScore = document.getElementById('pronunciation-score');
    const wordsAnalyzed = document.getElementById('words-analyzed');
    const wordComparisons = document.getElementById('word-comparisons');
    const currentWord = document.getElementById('current-word');
    const currentSentence = document.getElementById('current-sentence');
    const sentenceAudioSection = document.getElementById('sentence-audio-section');
 
    let fullAudioData = {
        analysis: {
            sentence_boundaries: []
        }
    };
 
    async function loadAudiosAndAnalyze() {
        try {
            message.textContent = 'Loading audio files...';
            const audioResponse = await fetch('/conversation_analysis/audio-analysis/generate-audio/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `room_sid=${encodeURIComponent(window.ROOM_SID)}&transcript=${encodeURIComponent(window.TRANSCRIPT)}`
            });
 
            const audioData = await audioResponse.json();
            if (audioData.error) throw new Error(audioData.error);
 
            const modelPath = `/conversation_analysis/audio-analysis/get-audio/${audioData.audio_path.split('/').pop()}`;
            const learnerPath = `/conversation_analysis/audio-analysis/get-audio/${audioData.audio_path_recorded.split('/').pop()}`;
 
            modelAudio.src = modelPath;
            learnerAudio.src = learnerPath;
            
            await new Promise(resolve => {
                const loadPromises = [
                    new Promise(res => modelAudio.addEventListener('loadeddata', res, {once: true})),
                    new Promise(res => learnerAudio.addEventListener('loadeddata', res, {once: true}))
                ];
                Promise.all(loadPromises).then(resolve);
            });
 
            message.textContent = 'Analyzing pronunciation...';
 
            const analysisResponse = await fetch('/conversation_analysis/audio-analysis/analyze/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `room_sid=${encodeURIComponent(window.ROOM_SID)}&transcript=${encodeURIComponent(window.TRANSCRIPT)}`
            });
 
            const analysisData = await analysisResponse.json();
            if (analysisData.error) throw new Error(analysisData.error);
 
            console.log('Analysis data received:', analysisData);
 
            updateAudioData(analysisData);
            displayAnalysisResults(analysisData);
            message.textContent = '';
 
        } catch (error) {
            message.textContent = `Error: ${error.message}`;
            console.error('Error:', error);
        }
    }
 
    function updateAudioData(analysisData) {
        fullAudioData = {
            model: modelAudio,
            learner: learnerAudio,
            analysis: {
                ...analysisData,
                sentence_boundaries: analysisData.sentence_boundaries || []
            }
        };
    }
 
    function displayAnalysisResults(data) {
        pronunciationScore.textContent = `${(data.score * 100).toFixed(1)}%`;
        wordsAnalyzed.textContent = `${data.total_words || '-'} words`;
 
        const problemWords = data.word_comparisons
            .filter(comp => comp.difference_score > 150)
            .slice(0, 5)
            .map(comp => {
                const score = ((1 - comp.difference_score/1000) * 100).toFixed(1);
                return `<div class="word-item" 
                    data-word="${comp.word}"
                    data-start="${comp.start_time}"
                    data-end="${comp.end_time}">
                    ${comp.word} (${score}%)
                </div>`;
            }).join('');
        wordComparisons.innerHTML = problemWords;
 
        document.querySelectorAll('.word-item').forEach(item => {
            item.addEventListener('click', () => playWordComparison(item));
        });
    }
 
    function playWordComparison(wordElement) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) {
            console.error('Web Audio API is not supported');
            return;
        }
    
        const audioContext = new AudioContext();
        const word = wordElement.dataset.word;
        let start = parseFloat(wordElement.dataset.start);
        let end = parseFloat(wordElement.dataset.end);
    
        async function processAndPlayAudio() {
            try {
                console.log(`Processing word: "${word}" from ${start}s to ${end}s`);
                
                // 時間範囲の検証と修正
                if (start === end) {
                    console.warn(`Zero duration detected for word: ${word}`);
                    // 最小の時間範囲を設定（0.5秒）
                    end = start + 0.5;
                }
         
                const response = await fetch(modelAudio.src);
                const buffer = await response.arrayBuffer();
                const audioBuffer = await audioContext.decodeAudioData(buffer);
         
                // より広い文脈を取得（前後1秒）
                const contextStart = Math.max(0, start - 1);
                const contextEnd = Math.min(end + 1, audioBuffer.duration);
         
                console.log(`Audio buffer info:`, {
                    duration: audioBuffer.duration,
                    sampleRate: audioBuffer.sampleRate,
                    numberOfChannels: audioBuffer.numberOfChannels,
                    contextStart,
                    contextEnd
                });
         
                const startSample = Math.floor(contextStart * audioBuffer.sampleRate);
                const endSample = Math.floor(contextEnd * audioBuffer.sampleRate);
         
                // バッファ範囲の検証
                if (startSample >= endSample) {
                    throw new Error(`Invalid time range: ${contextStart}s - ${contextEnd}s`);
                }
         
                const length = endSample - startSample;
                
                // より詳細なデバッグ情報
                console.log(`Buffer details:`, {
                    startSample,
                    endSample,
                    length,
                    maxLength: audioBuffer.length
                });
         
                const segmentBuffer = audioContext.createBuffer(
                    audioBuffer.numberOfChannels,
                    length,
                    audioBuffer.sampleRate
                );
         
                // データをコピー
                for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
                    const channelData = audioBuffer.getChannelData(channel);
                    const segment = channelData.subarray(startSample, endSample);
                    segmentBuffer.copyToChannel(segment, channel);
                }
         
                // UIの更新
                wordElement.classList.add('playing');
                currentWord.textContent = word;
         
                // 文脈を表示
                const sentence = window.TRANSCRIPT.split(/[.!?]+/)
                    .find(s => s.toLowerCase().includes(word.toLowerCase()));
                if (sentence) {
                    currentSentence.textContent = sentence.trim() + '.';
                }
                sentenceAudioSection.style.display = 'block';
         
                // 再生
                const source = audioContext.createBufferSource();
                source.buffer = segmentBuffer;
                source.connect(audioContext.destination);
                source.start(0);
         
                // 単語のハイライトタイミング
                const wordOffset = start - contextStart;
                setTimeout(() => {
                    wordElement.classList.add('highlight');
                    setTimeout(() => {
                        wordElement.classList.remove('highlight');
                    }, (end - start) * 1000);
                }, wordOffset * 1000);
         
                // 再生終了時の処理
                source.onended = () => {
                    wordElement.classList.remove('playing', 'highlight');
                };
         
                console.log('Audio playback started successfully');
         
            } catch (error) {
                console.error('Audio processing error:', error);
                console.log('Full error details:', {
                    word,
                    start,
                    end,
                    audioContext: audioContext?.state,
                    error: error.message
                });
                wordElement.classList.remove('playing', 'highlight');
                message.textContent = `Error playing audio: ${error.message}`;
            }
         }
    
        // 既存の再生を停止
        document.querySelectorAll('.word-item').forEach(item => {
            item.classList.remove('playing', 'highlight');
        });
    
        processAndPlayAudio();
    }
 
    loadAudiosAndAnalyze();
 });