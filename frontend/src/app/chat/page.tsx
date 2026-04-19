'use client';
import { useState, useRef, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { chatQuery, getReports, type ReportSummary, type SourceRef } from '@/lib/api';

type Message = {
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceRef[];
};

const AGENT_LABELS: Record<string, string> = {
  agent1: 'Demographics',
  agent2: 'Product Mix',
  agent3: 'Holiday Calendar',
  agent4: 'Vendor Picks',
};

const CHUNK_LABELS: Record<string, string> = {
  area_overview: 'Area Overview',
  race_demographics: 'Race & Ethnicity',
  religion_demographics: 'Religion',
  age_demographics: 'Age Groups',
  product_category: 'Category',
  holiday_event: 'Holiday Event',
  vendor_recommendation: 'Vendor',
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso;
  }
}

function renderContent(content: string) {
  return content.split('\n').map((line, i) => {
    const html = line
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/•/g, '•');
    return (
      <p
        key={i}
        className={line === '' ? 'mt-2' : ''}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  });
}

function SourcePills({ sources }: { sources: SourceRef[] }) {
  const seen = new Set<string>();
  const unique = sources.filter((s) => {
    const key = `${s.agent}:${s.chunk_type}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (!unique.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {unique.map((s, i) => (
        <span
          key={i}
          className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-600 ring-1 ring-brand-100"
        >
          {AGENT_LABELS[s.agent] ?? s.agent} · {CHUNK_LABELS[s.chunk_type] ?? s.chunk_type}
        </span>
      ))}
    </div>
  );
}

const STARTERS = [
  'Which vendors should I contact first?',
  'What holidays are coming up soon?',
  'What products should I prioritize?',
  'Tell me about my neighborhood demographics.',
];

export default function ChatPage() {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [reportsLoading, setReportsLoading] = useState(true);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load saved reports and restore last session from localStorage
  useEffect(() => {
    setReportsLoading(true);
    getReports()
      .then((data) => {
        setReports(data);
        const lastSession = typeof window !== 'undefined'
          ? localStorage.getItem('bodega_last_session')
          : null;
        if (lastSession && data.some((r) => r.session_id === lastSession)) {
          setActiveSession(lastSession);
        } else if (data.length > 0) {
          setActiveSession(data[0].session_id);
        }
      })
      .catch((e: Error) => setReportsError(e.message))
      .finally(() => setReportsLoading(false));
  }, []);

  // Reset conversation when the active report changes
  useEffect(() => {
    const active = reports.find((r) => r.session_id === activeSession);
    if (!active) return;
    setMessages([
      {
        role: 'assistant',
        content: `Hello! I have access to the **${active.store_name}** report (ZIP ${active.zip}, ${formatDate(active.generated_at)}). Ask me anything — which products to stock, which vendors to call, upcoming holidays to prepare for, or how your neighborhood demographics affect buying patterns.`,
      },
    ]);
  }, [activeSession, reports]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const activeReport = reports.find((r) => r.session_id === activeSession) ?? null;

  const send = useCallback(
    (text?: string) => {
      const content = (text ?? input).trim();
      if (!content || loading) return;
      setMessages((m) => [...m, { role: 'user', content }]);
      setInput('');
      setLoading(true);
      chatQuery(content, activeSession ?? undefined, activeReport?.zip)
        .then((res) => {
          setMessages((m) => [
            ...m,
            { role: 'assistant', content: res.answer, sources: res.sources },
          ]);
        })
        .catch((err: Error) => {
          setMessages((m) => [
            ...m,
            { role: 'assistant', content: `Sorry, something went wrong: ${err.message}` },
          ]);
        })
        .finally(() => setLoading(false));
    },
    [input, loading, activeSession, activeReport],
  );

  return (
    <div className="flex h-screen bg-slate-50">
      {/* ── Sidebar ─────────────────────────────────────────────────────────── */}
      <aside className="hidden w-64 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="border-b border-slate-200 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Saved Reports
          </p>
        </div>

        <div className="flex-1 space-y-1 overflow-y-auto p-3">
          {reportsLoading && (
            <div className="space-y-2 p-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-100" />
              ))}
            </div>
          )}
          {!reportsLoading && reportsError && (
            <p className="px-3 py-2 text-xs text-red-500">{reportsError}</p>
          )}
          {!reportsLoading && !reportsError && reports.length === 0 && (
            <p className="px-3 py-2 text-xs text-slate-400">
              No reports yet. Run the wizard to generate one.
            </p>
          )}
          {reports.map((r) => {
            const isActive = r.session_id === activeSession;
            return (
              <button
                key={r.session_id}
                onClick={() => setActiveSession(r.session_id)}
                className={`w-full rounded-lg px-3 py-2.5 text-left transition-all ${
                  isActive ? 'bg-brand-50 ring-1 ring-brand-200' : 'hover:bg-slate-50'
                }`}
              >
                <p className={`text-sm font-medium ${isActive ? 'text-brand-700' : 'text-slate-600'}`}>
                  {r.store_name}
                </p>
                <p className="mt-0.5 text-xs text-slate-400">
                  ZIP {r.zip} &middot; {formatDate(r.generated_at)}
                </p>
              </button>
            );
          })}
        </div>

        <div className="border-t border-slate-200 p-3">
          <Link
            href="/wizard"
            className="block w-full rounded-lg border border-slate-200 py-2 text-center text-xs font-medium text-slate-500 transition-colors hover:border-brand-300 hover:text-brand-700"
          >
            + Generate New Report
          </Link>
        </div>
      </aside>

      {/* ── Chat area ────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <div className="border-b border-slate-200 bg-white px-4 py-3 md:px-6 md:py-4">
          {/* Mobile report picker */}
          {reports.length > 0 && (
            <div className="mb-2 md:hidden">
              <select
                value={activeSession ?? ''}
                onChange={(e) => setActiveSession(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700 focus:border-brand-400 focus:outline-none"
              >
                {reports.map((r) => (
                  <option key={r.session_id} value={r.session_id}>
                    {r.store_name} — ZIP {r.zip}
                  </option>
                ))}
              </select>
            </div>
          )}
          {activeReport ? (
            <>
              <p className="text-sm font-semibold text-slate-800">{activeReport.store_name}</p>
              <p className="text-xs text-slate-400">
                ZIP {activeReport.zip} &middot; {formatDate(activeReport.generated_at)} &middot; Grounded answers only
              </p>
            </>
          ) : (
            <p className="text-sm text-slate-400">
              {reportsLoading ? 'Loading reports…' : 'No report selected'}
            </p>
          )}
        </div>

        {/* Empty state — no reports at all */}
        {!reportsLoading && reports.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-100">
              <span className="text-2xl font-bold text-brand-600">B</span>
            </div>
            <div>
              <p className="text-base font-semibold text-slate-800">No reports yet</p>
              <p className="mt-1 text-sm text-slate-500">
                Run the wizard first to generate a report — then come back here to chat with your data.
              </p>
            </div>
            <Link
              href="/wizard"
              className="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
            >
              Run Report Wizard
            </Link>
          </div>
        )}

        {/* Messages */}
        {(reportsLoading || reports.length > 0) && (
          <div className="flex-1 overflow-y-auto space-y-4 px-4 py-6 md:px-6">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {m.role === 'assistant' && (
                  <div className="mr-2 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100">
                    <span className="text-xs font-bold text-brand-700">B</span>
                  </div>
                )}
                <div className="max-w-xl">
                  <div
                    className={`space-y-0.5 rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      m.role === 'user'
                        ? 'rounded-tr-sm bg-brand-600 text-white'
                        : 'rounded-tl-sm bg-white text-slate-700 shadow-sm ring-1 ring-slate-100'
                    }`}
                  >
                    {renderContent(m.content)}
                  </div>
                  {m.role === 'assistant' && m.sources && (
                    <SourcePills sources={m.sources} />
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="mr-2 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100">
                  <span className="text-xs font-bold text-brand-700">B</span>
                </div>
                <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-slate-100">
                  {[0, 1, 2].map((j) => (
                    <span
                      key={j}
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-300"
                      style={{ animationDelay: `${j * 150}ms` }}
                    />
                  ))}
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}

        {/* Starter questions */}
        {messages.length === 1 && activeReport && (
          <div className="flex flex-wrap gap-2 px-4 pb-3 md:px-6">
            {STARTERS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500 transition-colors hover:border-brand-300 hover:text-brand-700"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        {(reportsLoading || reports.length > 0) && (
          <div className="border-t border-slate-200 bg-white px-4 py-4 md:px-6">
            <div className="flex gap-3">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder={activeReport ? `Ask about ${activeReport.store_name}…` : 'Select a report to start chatting…'}
                disabled={!activeReport || loading}
                rows={1}
                className="flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-50"
              />
              <button
                onClick={() => send()}
                disabled={!input.trim() || loading || !activeReport}
                className="rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-brand-700 disabled:opacity-40"
              >
                Send
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-400">
              Answers are grounded in your saved report data — not generic AI knowledge.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
