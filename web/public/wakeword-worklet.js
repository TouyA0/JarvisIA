// AudioWorkletProcessor : tourne hors du thread principal, accumule
// l'audio du micro par petits blocs et les transmet au thread principal
// (qui gère la fenêtre glissante et le scoring — voir useWakeWord.js).
// Pas de logique de détection ici, juste de la capture.
const CHUNK_SAMPLES = 512; // même granularité que agents/desktop/audio (chunk_size=512)

class WakeWordCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(CHUNK_SAMPLES);
    this._offset = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0]; // mono
    if (!channel) return true;

    for (let i = 0; i < channel.length; i++) {
      this._buffer[this._offset++] = channel[i];
      if (this._offset >= CHUNK_SAMPLES) {
        this.port.postMessage(this._buffer.slice(0));
        this._offset = 0;
      }
    }
    return true;
  }
}

registerProcessor("wakeword-capture", WakeWordCapture);
