/** PCM16 mic capture + playback at 24 kHz, matching OpenAI Realtime's native format. */

export type AudioCapture = {
  stop: () => void;
  analyser: AnalyserNode;
};

export async function startCapture(onChunk: (buf: ArrayBuffer) => void): Promise<AudioCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
  const ctx = new AudioContext({ sampleRate: 24000 });
  await ctx.audioWorklet.addModule("/pcm-worklet.js");
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 64;
  src.connect(analyser);
  const node = new AudioWorkletNode(ctx, "pcm-worklet");
  src.connect(node);
  node.port.onmessage = (e) => onChunk(e.data);
  return {
    stop: () => {
      node.disconnect();
      analyser.disconnect();
      src.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
    },
    analyser,
  };
}

export class PCMPlayer {
  private ctx: AudioContext;
  private nextStart = 0;

  constructor(sampleRate = 24000) {
    this.ctx = new AudioContext({ sampleRate });
  }

  /** Enqueue a PCM16 LE chunk for playback. Plays sequentially. */
  play(buf: ArrayBuffer) {
    const view = new DataView(buf);
    const samples = buf.byteLength / 2;
    const audioBuf = this.ctx.createBuffer(1, samples, this.ctx.sampleRate);
    const channel = audioBuf.getChannelData(0);
    for (let i = 0; i < samples; i++) {
      const int16 = view.getInt16(i * 2, true);
      channel[i] = int16 / (int16 < 0 ? 0x8000 : 0x7FFF);
    }
    const src = this.ctx.createBufferSource();
    src.buffer = audioBuf;
    src.connect(this.ctx.destination);
    const startAt = Math.max(this.ctx.currentTime, this.nextStart);
    src.start(startAt);
    this.nextStart = startAt + audioBuf.duration;
  }

  /** Stop everything immediately (used for barge-in). */
  clear() {
    this.nextStart = this.ctx.currentTime;
  }

  close() {
    this.ctx.close();
  }
}
