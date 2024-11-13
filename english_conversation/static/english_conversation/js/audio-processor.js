class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 2048;
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (!input || !input[0]) return true;

        const inputChannel = input[0];
        
        for (let i = 0; i < inputChannel.length; i++) {
            this.buffer[this.bufferIndex] = inputChannel[i];
            this.bufferIndex++;

            if (this.bufferIndex >= this.bufferSize) {
                // Float32からInt16に変換
                const pcmData = new Int16Array(this.bufferSize);
                for (let j = 0; j < this.bufferSize; j++) {
                    // 値を[-1,1]から[-32768,32767]に変換
                    const s = Math.max(-1, Math.min(1, this.buffer[j]));
                    pcmData[j] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }
                
                // 配列として送信
                this.port.postMessage([...pcmData]);
                
                this.bufferIndex = 0;
            }
        }

        return true;
    }
}

registerProcessor('audio-processor', AudioProcessor);