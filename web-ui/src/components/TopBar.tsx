import { useStore } from "../state/store";
import { Select } from "./ui/select";
import { Input } from "./ui/input";
import { textWs } from "../lib/ws";

export function TopBar() {
  const { provider, model, setProvider, setModel } = useStore();
  return (
    <div className="flex items-center gap-3 px-4 h-14 border-b border-border bg-bg">
      <div className="font-display font-semibold tracking-tight text-base">
        elyos <span className="bg-accent-gradient bg-clip-text text-transparent">chat</span>
      </div>
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
    </div>
  );
}
