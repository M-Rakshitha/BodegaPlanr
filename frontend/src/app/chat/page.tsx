'use client';
import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';

type Message = { role: 'user' | 'assistant'; content: string };

const savedReports = [
  { id: 1, name: 'Morales Corner Store', zip: '10031', date: 'Apr 18, 2026', active: true },
  { id: 2, name: 'Uptown Deli', zip: '10040', date: 'Apr 12, 2026', active: false },
];

const initialMessages: Message[] = [
  {
    role: 'assistant',
    content:
      "Hello! I have access to the Morales Corner Store report (ZIP 10031, Apr 18). Ask me anything — which products to stock, which vendors to call, upcoming holidays to prepare for, or how your neighborhood demographics affect buying patterns.",
  },
];

const mockReplies: Array<{ keywords: string[]; reply: string }> = [
  {
    keywords: ['vendor', 'distributor', 'supplier', 'contact', 'order'],
    reply:
      "Based on your report, your top distributor contacts are:\n\n• **UNFI** — for Goya Coconut Water and Dove Soap (score 97 and 80). Contact your local UNFI rep to set up a net-30 account.\n• **DSD Direct** — Monster Energy and Lay's deliver directly via route sales. Call the local Monster route manager for pricing.\n• **McLane** — for Bounty and Pantene. They have a 1-case minimum and next-day delivery in NYC.\n\nGoya items can also be ordered direct at better unit economics if your volume is above 10 cases/week.",
  },
  {
    keywords: ['holiday', 'eid', 'easter', 'christmas', 'stock', 'upcoming', 'calendar'],
    reply:
      "Your next three stocking events:\n\n• **Eid al-Fitr (Apr 27)** — Stock halal sweets, dates, and greeting cards by April 13. Your 4 Muslim congregations nearby make this high-priority.\n• **Mother's Day (May 10)** — Stock flowers, candy, and cards by May 8.\n• **Memorial Day (May 25)** — Biggest beverage day of Q2. Pre-order 20–30% more Monster, soda, and ice by May 15.\n\nAll 9 holidays with stocking notes are in your full report.",
  },
  {
    keywords: ['product', 'category', 'sell', 'carry', 'stock', 'top', 'best'],
    reply:
      "Your top 3 categories by AI score for ZIP 10031:\n\n1. **Beverages** (96) — High foot traffic + large young adult population. Prioritize single-serve energy drinks and coconut water.\n2. **Snacks & Chips** (91) — Largest CEX spend category for urban households at your income level.\n3. **Latin / Caribbean Foods** (88) — 52% Hispanic population means Goya, sofrito, and sazón are near-guaranteed sellers.\n\nPersonal Care (82) and Prepared Foods (79) round out your top 5.",
  },
  {
    keywords: ['demographic', 'neighborhood', 'population', 'income', 'who'],
    reply:
      "Your ZIP 10031 (Hamilton Heights / Harlem) profile:\n\n• **47,234** total residents · **$38,500** median household income\n• **52% Hispanic / Latino** — strongest affinity group for your inventory\n• **89% renters** — means single-serve packaging and small quantities outperform bulk\n• **28% below poverty line** — value-tier SKUs and small pack sizes are critical\n• 4 Muslim congregations, 14 Baptist/Pentecostal churches, 6 Catholic churches nearby\n\nThis is a highly walkable neighborhood with strong daily foot traffic — ideal for a bodega format.",
  },
  {
    keywords: ['halal', 'kosher', 'religious', 'muslim', 'jewish'],
    reply:
      "Your report flagged 4 Muslim congregations within 1 mile. For halal opportunities:\n\n• Stock halal-certified confections and snacks (look for the halal seal)\n• Dates are year-round sellers — not just Ramadan. Buy through your UNFI account.\n• For Eid al-Fitr (Apr 27) and Eid al-Adha (Jun 15), stock greeting cards and gift-wrapped items 2 weeks ahead.\n\nFor kosher, you have 1 Jewish congregation nearby — lower priority but worth stocking Passover basics in April.",
  },
];

function getMockReply(input: string): string {
  const lower = input.toLowerCase();
  for (const { keywords, reply } of mockReplies) {
    if (keywords.some((kw) => lower.includes(kw))) return reply;
  }
  return "Based on your Morales Corner Store report, the neighborhood has a 52% Hispanic population with a median income of $38,500 and an 89% renter rate. The top recommendation is to focus on Beverages, Latin Foods, and Snacks — all scoring above 88 — while keeping pack sizes small and value-oriented. Is there a specific agent or section of the report you want to dig into?";
}

function renderMessage(content: string) {
  return content.split('\n').map((line, i) => {
    const bold = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    return (
      <p key={i} className={line === '' ? 'mt-2' : ''} dangerouslySetInnerHTML={{ __html: bold }} />
    );
  });
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || loading) return;
    setMessages((m) => [...m, { role: 'user', content }]);
    setInput('');
    setLoading(true);
    setTimeout(() => {
      setMessages((m) => [...m, { role: 'assistant', content: getMockReply(content) }]);
      setLoading(false);
    }, 1100);
  };

  const starters = [
    'Which vendors should I contact first?',
    'What holidays are coming up soon?',
    'What products should I prioritize?',
    'Tell me about my neighborhood demographics.',
  ];

  return (
    <div className="flex h-[calc(100vh-56px)] bg-slate-50">
      {/* Sidebar */}
      <aside className="hidden w-64 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="border-b border-slate-200 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Saved Reports</p>
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto p-3">
          {savedReports.map((r) => (
            <button
              key={r.id}
              className={`w-full rounded-lg px-3 py-2.5 text-left transition-all ${
                r.active
                  ? 'bg-green-50 ring-1 ring-green-200'
                  : 'hover:bg-slate-50'
              }`}
            >
              <p className={`text-sm font-medium ${r.active ? 'text-green-700' : 'text-slate-600'}`}>
                {r.name}
              </p>
              <p className="mt-0.5 text-xs text-slate-400">ZIP {r.zip} &middot; {r.date}</p>
            </button>
          ))}
        </div>
        <div className="border-t border-slate-200 p-3">
          <Link
            href="/wizard"
            className="block w-full rounded-lg border border-slate-200 py-2 text-center text-xs font-medium text-slate-500 transition-colors hover:border-green-300 hover:text-green-700"
          >
            + Generate New Report
          </Link>
        </div>
      </aside>

      {/* Chat area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <div className="border-b border-slate-200 bg-white px-6 py-4">
          <p className="text-sm font-semibold text-slate-800">Morales Corner Store</p>
          <p className="text-xs text-slate-400">ZIP 10031 &middot; Report from Apr 18, 2026 &middot; Grounded answers only</p>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto space-y-4 px-6 py-6">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {m.role === 'assistant' && (
                <div className="mr-2 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green-100">
                  <span className="text-xs font-bold text-green-700">B</span>
                </div>
              )}
              <div
                className={`max-w-xl space-y-0.5 rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'rounded-tr-sm bg-green-600 text-white'
                    : 'rounded-tl-sm bg-white text-slate-700 shadow-sm ring-1 ring-slate-100'
                }`}
              >
                {renderMessage(m.content)}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="mr-2 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green-100">
                <span className="text-xs font-bold text-green-700">B</span>
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

        {/* Starter suggestions */}
        {messages.length === 1 && (
          <div className="flex flex-wrap gap-2 px-6 pb-3">
            {starters.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500 transition-colors hover:border-green-300 hover:text-green-700"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="border-t border-slate-200 bg-white px-6 py-4">
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
              placeholder="Ask about your report..."
              rows={1}
              className="flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-green-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-green-400"
            />
            <button
              onClick={() => send()}
              disabled={!input.trim() || loading}
              className="rounded-xl bg-green-600 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-green-700 disabled:opacity-40"
            >
              Send
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            Answers are grounded in your saved report — not generic AI knowledge.
          </p>
        </div>
      </div>
    </div>
  );
}
