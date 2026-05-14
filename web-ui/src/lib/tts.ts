/** Browser-native TTS using SpeechSynthesis. Splits text into sentences and queues them. */
let buffer = "";

export function feedDelta(delta: string) {
  buffer += delta;
  const re = /[.!?\n]+/g;
  let lastEnd = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(buffer))) {
    const chunk = buffer.slice(lastEnd, m.index + m[0].length).trim();
    if (chunk) speak(chunk);
    lastEnd = m.index + m[0].length;
  }
  buffer = buffer.slice(lastEnd);
}

export function flush() {
  const rest = buffer.trim();
  buffer = "";
  if (rest) speak(rest);
}

export function cancel() {
  buffer = "";
  window.speechSynthesis.cancel();
}

function speak(text: string) {
  const u = new SpeechSynthesisUtterance(text);
  window.speechSynthesis.speak(u);
}
