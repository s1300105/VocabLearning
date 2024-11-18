document.addEventListener('DOMContentLoaded', function() {
    const modelAudio = document.getElementById('model-audio');
    const learnerAudio = document.getElementById('learner-audio');
    const message = document.getElementById('message');

    async function loadAudios() {
        try {
            message.textContent = 'Loading audio files...';
            const response = await fetch('/conversation_analysis/audio-analysis/generate-audio/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `room_sid=${encodeURIComponent(window.ROOM_SID)}&transcript=${encodeURIComponent(window.TRANSCRIPT)}`
            });

            const data = await response.json();
            if (data.error) throw new Error(data.error);

            modelAudio.src = `/conversation_analysis/audio-analysis/get-audio/${data.audio_path.split('/').pop()}`;
            learnerAudio.src = `/conversation_analysis/audio-analysis/get-audio/${data.audio_path_recorded.split('/').pop()}`;
            
            await Promise.all([modelAudio.load(), learnerAudio.load()]);
            message.textContent = '';
        } catch (error) {
            message.textContent = `Error: ${error.message}`;
        }
    }

    loadAudios();
});