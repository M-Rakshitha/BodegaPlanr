const buildOrder = [
  "Agent 1: Demographic Profiler (Census + ARDA)",
  "Agent 2: Buying Behavior Suggester (rules + CEX)",
  "Agent 3: Religious Holiday Calendar (Hebcal + Aladhan)",
  "Agent 4: Vendor & Inventory Recommender (RangeMe/Faire/UNFI)",
];

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-50">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        <header className="space-y-3">
          <p className="text-sm font-semibold uppercase tracking-widest text-teal-300">
            BodegaPlanr
          </p>
          <h1 className="text-4xl font-bold tracking-tight">
            Corner Store Planning — Starter App
          </h1>
          <p className="max-w-3xl text-slate-300">
            Initial project scaffold with a Next.js frontend and FastAPI backend for the
            4-agent planning workflow.
          </p>
        </header>

        <section className="grid gap-4 md:grid-cols-2">
          <article className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
            <h2 className="text-xl font-semibold">Frontend Wizard (planned)</h2>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-slate-300">
              <li>Step 0: Address / ZIP input</li>
              <li>Step 1: Demographic cards + filters</li>
              <li>Step 2: Product category ranking</li>
              <li>Step 3: 90-day holiday calendar</li>
              <li>Step 4: Vendor + pricing table</li>
            </ul>
          </article>

          <article className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
            <h2 className="text-xl font-semibold">MVP Build Order</h2>
            <ol className="mt-3 list-decimal space-y-1 pl-5 text-slate-300">
              {buildOrder.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ol>
          </article>
        </section>
      </div>
    </main>
  );
}
