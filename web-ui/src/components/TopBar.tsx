import { useStore } from "../state/store";
import { Select } from "./ui/select";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { textWs } from "../lib/ws";
import { voiceWs } from "../lib/voice";
import { Mic, Volume2, VolumeX } from "lucide-react";

export function TopBar() {
  const { provider, model, ttsEnabled, mode, setProvider, setModel, toggleTts } = useStore();
  const inVoice = mode === "voice-active";
  return (
    <div className="flex items-center gap-3 px-4 h-12 border-b border-border bg-bg">
      <div className="font-semibold">elyos chat</div>
      <div className="flex-1" />
      <Select value={provider} onChange={(e) => { setProvider(e.target.value as any); textWs.updateSettings(e.target.value); }}>
        <option value="anthropic">Anthropic</option>
        <option value="openai">OpenAI</option>
        <option value="gemini">Gemini</option>
      </Select>
      <Input
        className="w-56"
        placeholder="model (optional)"
        value={model ?? ""}
        onChange={(e) => { setModel(e.target.value || null); textWs.updateSettings(undefined, e.target.value || null); }}
      />
      <Button variant="ghost" size="icon" onClick={toggleTts} title={ttsEnabled ? "TTS on" : "TTS off"}>
        {ttsEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
      </Button>
      <Button
        variant={inVoice ? "danger" : "ghost"}
        size="icon"
        onClick={() => inVoice ? voiceWs.stop() : voiceWs.start(useStore.getState().sessionId ?? "last")}
        title={inVoice ? "stop voice mode" : "start voice mode"}
      >
        <Mic size={16} />
      </Button>
    </div>
  );
}
