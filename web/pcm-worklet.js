// Browser audio stays PCM; the ASR streaming policy is supplied by WhisperLiveKit.
class PCM extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Int16Array(1600);
    this.offset = 0;
    this.closed = false;
    this.port.onmessage = e => {
      if (e.data.type === 'flush') {
        this.closed = true;
        if (this.offset) {
          const tail = this.chunk.slice(0, this.offset);
          this.port.postMessage(tail.buffer, [tail.buffer]);
          this.offset = 0;
        }
        this.port.postMessage({
          type: 'flushed'
        });
      }
    };
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input || this.closed) return true;
    for (const sample of input) {
      this.chunk[this.offset++] = Math.round(Math.max(-1, Math.min(1, sample)) * 32767);
      if (this.offset === 1600) {
        this.port.postMessage(this.chunk.buffer, [this.chunk.buffer]);
        this.chunk = new Int16Array(1600);
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor('pcm-capture', PCM);
