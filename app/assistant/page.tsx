"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, FileText, Send, User as UserIcon } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { AuthRequired, PageHeader, Spinner } from "@/components/ui";

interface Message {
  role: "user" | "assistant";
  content: string;
  isError?: boolean;
}

const GREETING: Message = {
  role: "assistant",
  content:
    "AegisAI intelligence assistant ready. Ask about recorded detections, threat scores or sector activity.",
};

export default function AssistantPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([GREETING]);
  const [isBusy, setBusy] = useState(false);
  const [isOnline, setOnline] = useState<boolean | null>(true);

  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.assistant.status()
      .then((r) => setOnline(r.online ?? true))
      .catch(() => setOnline(true));
  }, []);

  // Keep the newest message visible. The old build never scrolled, so replies
  // appeared below the fold with no indication anything had happened.
  useEffect(() => {
    logRef.current?.scrollTo({
      top: logRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isBusy]);

  const send = useCallback(
    async (action: "ask" | "report") => {
      const question = query.trim();
      if (action === "ask" && !question) return;

      const prompt = action === "ask"
        ? question
        : "Generate a tactical intelligence report.";

      setMessages((prev) => [...prev, { role: "user", content: prompt }]);
      setQuery("");
      setBusy(true);

      try {
        const response = action === "ask"
          ? await api.assistant.ask(question)
          : await api.assistant.report();
        const content = "answer" in response ? response.answer : response.content;
        setOnline(response.online ?? true);
        setMessages((prev) => [...prev, { role: "assistant", content }]);
      } catch (err) {
        setMessages((prev) => [...prev, {
          role: "assistant",
          content: err instanceof ApiError ? err.message : "The request failed.",
          isError: true,
        }]);
      } finally {
        setBusy(false);
        inputRef.current?.focus();
      }
    },
    [query],
  );

  if (authLoading) return <Spinner label="Checking session" />;
  if (!isAuthenticated) return <AuthRequired />;

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] min-h-[520px]">
      <PageHeader
        eyebrow="Aegis Llama-3 AI Engine"
        icon={Bot}
        title="Generative"
        accent="AI Assistant"
        actions={
          <button
            onClick={() => send("report")}
            disabled={isBusy}
            className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary text-aegis-bg font-bold hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            <FileText className="w-5 h-5" aria-hidden="true" />
            Auto-generate report
          </button>
        }
      />

      <div className="flex-1 glass-panel rounded-2xl flex flex-col overflow-hidden min-h-0">
        <div
          ref={logRef}
          className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5"
          role="log"
          aria-live="polite"
          aria-label="Conversation"
        >
          {messages.map((message, index) => {
            const isUser = message.role === "user";
            return (
              <div
                key={index}
                className={`flex items-start gap-3 sm:gap-4 ${isUser ? "flex-row-reverse" : ""}`}
              >
                <div
                  className={`w-9 h-9 shrink-0 rounded-full flex items-center justify-center ${
                    isUser
                      ? "bg-white/10 border border-white/20"
                      : "bg-gradient-to-br from-aegis-accent to-aegis-accent-secondary"
                  }`}
                >
                  {isUser
                    ? <UserIcon className="w-4 h-4 text-gray-300" aria-hidden="true" />
                    : <Bot className="w-5 h-5 text-aegis-bg" aria-hidden="true" />}
                </div>
                <div
                  className={`max-w-[85%] sm:max-w-[75%] p-4 rounded-2xl whitespace-pre-wrap text-sm leading-relaxed ${
                    isUser
                      ? "bg-white/10 text-white rounded-tr-sm border border-white/10"
                      : message.isError
                        ? "bg-aegis-danger/10 text-aegis-danger rounded-tl-sm border border-aegis-danger/30"
                        : "bg-black/40 text-gray-200 rounded-tl-sm border border-aegis-accent/20"
                  }`}
                >
                  <span className="sr-only">{isUser ? "You said: " : "Assistant said: "}</span>
                  {message.content}
                </div>
              </div>
            );
          })}

          {isBusy && (
            <div className="flex items-start gap-4">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-aegis-accent to-aegis-accent-secondary flex items-center justify-center">
                <Bot className="w-5 h-5 text-aegis-bg animate-pulse" aria-hidden="true" />
              </div>
              <div className="bg-black/40 p-4 rounded-2xl rounded-tl-sm border border-aegis-accent/20 flex gap-1.5 items-center">
                <span className="sr-only">Assistant is responding</span>
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="w-2 h-2 bg-aegis-accent rounded-full animate-bounce"
                    style={{ animationDelay: `${delay}ms` }}
                    aria-hidden="true"
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-white/10 bg-black/20">
          <form
            className="relative flex items-center"
            onSubmit={(e) => { e.preventDefault(); send("ask"); }}
          >
            <label htmlFor="assistant-input" className="sr-only">
              Ask the intelligence assistant
            </label>
            <input
              id="assistant-input"
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={isBusy}
              placeholder="Ask about threats, metrics or sector activity..."
              className="w-full bg-white/5 border border-white/10 rounded-2xl py-3.5 pl-5 pr-14 text-white placeholder-gray-500 focus:border-aegis-accent transition-colors disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={isBusy || !query.trim()}
              className="absolute right-2 p-2.5 bg-aegis-accent hover:bg-aegis-accent-secondary disabled:bg-white/10 disabled:text-gray-500 text-aegis-bg rounded-xl transition-colors"
              aria-label="Send message"
            >
              <Send className="w-4 h-4" aria-hidden="true" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
