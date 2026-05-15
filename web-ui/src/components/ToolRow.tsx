import { useState } from "react";
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronRight } from "lucide-react";

type Props = { name: string; pending: boolean; args?: any; result?: any; isError?: boolean; elapsed?: number };

export function ToolRow({ name, pending, result, isError, elapsed }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="my-2 rounded-md border border-border bg-bg/50">
      <button onClick={() => setOpen((x) => !x)} className="flex items-center gap-2 w-full px-3 py-2 text-sm">
        {pending ? <Loader2 size={14} className="animate-spin text-amber-600" /> :
          isError ? <XCircle size={14} className="text-red-600" /> : <CheckCircle2 size={14} className="text-green-600" />}
        <span className="font-mono text-xs text-muted">{name}</span>
        {pending && elapsed !== undefined && <span className="text-xs text-muted">{(elapsed / 1000).toFixed(1)}s</span>}
        <span className="flex-1" />
        {!pending && (open ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
      </button>
      {open && !pending && (
        <pre className="px-3 pb-2 text-xs font-mono text-muted whitespace-pre-wrap break-all">
{JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}
