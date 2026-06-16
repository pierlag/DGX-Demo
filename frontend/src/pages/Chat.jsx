import React, { useRef, useState } from "react";
import { MessagesSquare, Send, Timer, Zap, FileText, Bot, User } from "lucide-react";
import { Card, SectionTitle, Badge } from "../components/ui.jsx";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  const scroll = () =>
    setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [
      ...m,
      { role: "user", content: text },
      { role: "assistant", content: "", sources: [], toolCalls: [], meta: null },
    ]);
    scroll();

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, use_rag: useRag, top_k: 4 }),
      });
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const obj = JSON.parse(line);
          setMessages((m) => {
            const copy = [...m];
            const i = copy.length - 1;
            const last = { ...copy[i] };
            if (obj.type === "sources") last.sources = obj.sources;
            else if (obj.type === "token") last.content += obj.text;
            else if (obj.type === "tool_calls") {
              last.toolCalls = [...(last.toolCalls || []), ...(obj.tool_calls || [])];
            }
            else if (obj.type === "error") last.content += `\n⚠️ ${obj.text}`;
            else if (obj.type === "done")
              last.meta = {
                latency: obj.latency_ms,
                tin: obj.tokens_in,
                tout: obj.tokens_out,
              };
            copy[i] = last;
            return copy;
          });
          scroll();
        }
      }
    } catch (e) {
      setMessages((m) => {
        const copy = [...m];
        const i = copy.length - 1;
        const last = { ...copy[i] };
        last.content += `\n⚠️ Erreur: ${e.message}`;
        copy[i] = last;
        return copy;
      });
    } finally {
      setBusy(false);
      scroll();
    }
  };

  return (
    <div className="flex h-[calc(100dvh-7rem)] flex-col space-y-3 sm:space-y-4 lg:h-[calc(100vh-3rem)]">
      <SectionTitle
        icon={MessagesSquare}
        title="Chat de test · Serveur MCP RAG"
        subtitle="Validez localement la chaîne RAG + vLLM"
        right={
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={useRag}
              onChange={(e) => setUseRag(e.target.checked)}
            />
            RAG activé
          </label>
        }
      />

      <Card className="flex flex-1 flex-col overflow-hidden p-0">
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="grid h-full place-items-center text-center text-slate-500">
              <div>
                <MessagesSquare size={40} className="mx-auto mb-2 opacity-40" />
                <p>Posez une question sur vos documents indexés.</p>
              </div>
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}
            >
              {msg.role === "assistant" && (
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand/15 text-brand">
                  <Bot size={16} />
                </div>
              )}
              <div className={`max-w-[85%] sm:max-w-[75%] ${msg.role === "user" ? "order-1" : ""}`}>
                <div
                  className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${
                    msg.role === "user"
                      ? "bg-brand text-black"
                      : "border border-ink-border bg-ink-900/60 text-slate-100"
                  }`}
                >
                  {msg.content || (busy && i === messages.length - 1 ? "…" : "")}
                </div>
                {msg.sources?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {msg.sources.map((s, j) => (
                      <Badge key={j} tone="blue">
                        <FileText size={11} /> {s.source} · {s.score}
                      </Badge>
                    ))}
                  </div>
                )}
                {msg.toolCalls?.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {msg.toolCalls.map((tc, j) => (
                      <Badge key={j} tone="amber">
                        tool_call: {tc.function?.name || tc.id || "unknown"}
                      </Badge>
                    ))}
                  </div>
                )}
                {msg.meta && (
                  <div className="mt-1.5 flex gap-3 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <Timer size={12} /> {msg.meta.latency} ms
                    </span>
                    <span className="flex items-center gap-1">
                      <Zap size={12} /> {msg.meta.tin}→{msg.meta.tout} tokens
                    </span>
                  </div>
                )}
              </div>
              {msg.role === "user" && (
                <div className="order-2 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-ink-700 text-slate-300">
                  <User size={16} />
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="border-t border-ink-border p-3 sm:p-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              className="input"
              placeholder="Votre question…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              disabled={busy}
            />
            <button
              className="btn-primary shrink-0 justify-center"
              onClick={send}
              disabled={busy || !input.trim()}
            >
              <Send size={16} /> Envoyer
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
