# Frontend Integration: Live Backend Progress (WebSocket)

This guide shows how to display every backend orchestration step in real-time while `/orchestration/run` is executing.

## 1) Backend contract

### Start run

- Endpoint: `POST /orchestration/run`
- Body must include a client-generated `run_id`.

Example request body:

```json
{
  "run_id": "7b5f0e5e-6f2d-4df9-a2b0-5039db0e43f8",
  "address": "2121 I St NW, Washington, DC 20052",
  "include_religion": true
}
```

### Subscribe to progress

- WebSocket: `ws://localhost:8000/orchestration/ws/{run_id}`

Each message is JSON with this shape:

```json
{
  "timestamp": "2026-01-01T12:00:00.000000+00:00",
  "event": "agent2_completed",
  "run_id": "7b5f0e5e-6f2d-4df9-a2b0-5039db0e43f8",
  "stage": "agent2",
  "status": "completed",
  "message": "Agent 2 suggestions ready.",
  "data": {
    "categories_count": 4,
    "top_items_count": 18
  }
}
```

Common events include:

- `orchestration_queued`
- `orchestration_started`
- `agent1_started`, `agent1_completed`, `agent1_failed`
- `agent2_started`, `agent2_completed`, `agent2_failed`
- `agent3_started`, `agent3_completed`, `agent3_failed`
- `agent4_started`, `agent4_completed`, `agent4_failed`
- `orchestration_completed`
- `orchestration_response_ready`
- `orchestration_failed`

## 2) Add frontend event types

Create a shared type, for example in `src/types/orchestration-progress.ts`:

```ts
export type OrchestrationProgressEvent = {
  timestamp: string;
  event: string;
  run_id: string;
  stage: "orchestration" | "agent1" | "agent2" | "agent3" | "agent4";
  status: "queued" | "started" | "completed" | "failed" | "listening";
  message: string;
  data?: Record<string, unknown>;
};
```

## 3) React hook for live progress

Create `src/hooks/useOrchestrationProgress.ts`:

```ts
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { OrchestrationProgressEvent } from "@/types/orchestration-progress";

type UseOrchestrationProgressOptions = {
  runId: string | null;
  backendHttpBase: string; // e.g. http://localhost:8000
};

export function useOrchestrationProgress({
  runId,
  backendHttpBase,
}: UseOrchestrationProgressOptions) {
  const [events, setEvents] = useState<OrchestrationProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    const wsBase = backendHttpBase.replace(/^http/, "ws").replace(/\/$/, "");
    const ws = new WebSocket(`${wsBase}/orchestration/ws/${runId}`);
    socketRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    ws.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data) as OrchestrationProgressEvent;
        setEvents((prev) => [...prev, parsed]);
      } catch {
        // Ignore malformed payloads.
      }
    };

    return () => {
      ws.close();
      socketRef.current = null;
      setConnected(false);
    };
  }, [runId, backendHttpBase]);

  const latest = useMemo(
    () => (events.length ? events[events.length - 1] : null),
    [events],
  );

  return { events, latest, connected };
}
```

## 4) Start orchestration with the same run_id

In your action handler:

```ts
const runId = crypto.randomUUID();
setRunId(runId);

const response = await fetch(
  `${process.env.NEXT_PUBLIC_BACKEND_URL}/orchestration/run`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      address: "2121 I St NW, Washington, DC 20052",
      include_religion: true,
    }),
  },
);

const result = await response.json();
```

Important:

- Open the WebSocket as soon as `runId` is set.
- Then call `POST /orchestration/run` with the same `run_id`.

## 5) Render timeline UI

Minimal timeline example:

```tsx
{
  events.map((evt, idx) => (
    <div key={`${evt.timestamp}-${idx}`} className="rounded border p-3">
      <div className="text-xs opacity-70">
        {new Date(evt.timestamp).toLocaleTimeString()}
      </div>
      <div className="font-medium">
        {evt.stage} · {evt.status}
      </div>
      <div className="text-sm">{evt.message}</div>
      {evt.data ? (
        <pre className="text-xs mt-2">{JSON.stringify(evt.data, null, 2)}</pre>
      ) : null}
    </div>
  ));
}
```

## 6) UX recommendations

- Mark pipeline complete when `event === "orchestration_completed"`.
- Mark pipeline failed when any `status === "failed"`.
- Keep timeline visible after completion so users can inspect what happened.
- If the user reruns, reset the local `events` array and create a new `run_id`.
