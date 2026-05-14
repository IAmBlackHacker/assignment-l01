class PCMWorklet extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;
    const buf = new ArrayBuffer(channel.length * 2);
    const view = new DataView(buf);
    for (let i = 0; i < channel.length; i++) {
      let s = Math.max(-1, Math.min(1, channel[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    this.port.postMessage(buf, [buf]);
    return true;
  }
}
registerProcessor("pcm-worklet", PCMWorklet);
