import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import { voiceWs } from "../lib/voice";
import { Button } from "./ui/button";
import { Pause, Square } from "lucide-react";

export function VoiceBar() {
  const mode = useStore((s) => s.mode);
  const [bars, setBars] = useState<number[]>(new Array(32).fill(0));
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (mode !== "voice-active") return;
    const tick = () => {
      const a = voiceWs.analyser;
      if (a) {
        const data = new Uint8Array(a.frequencyBinCount);
        a.getByteFrequencyData(data);
        const next: number[] = new Array(32);
        const step = Math.floor(data.length / 32);
        for (let i = 0; i < 32; i++) next[i] = data[i * step] / 255;
        setBars(next);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [mode]);

  if (mode !== "voice-active") return null;

  return (
    <div className="border-t border-border p-3 flex items-center gap-3 bg-bg">
      <span className="text-sm text-muted">🎙️</span>
      <div className="flex-1 flex items-end gap-0.5 h-8">
        {bars.map((v, i) => (
          <div key={i} className="flex-1 bg-accent rounded-sm" style={{ height: `${Math.max(4, v * 100)}%` }} />
        ))}
      </div>
      <Button variant="ghost" size="icon" onClick={() => voiceWs.cancel()} title="interrupt"><Pause size={16} /></Button>
      <Button variant="danger" size="icon" onClick={() => voiceWs.stop()} title="stop voice mode"><Square size={16} /></Button>
    </div>
  );
}
