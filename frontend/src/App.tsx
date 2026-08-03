import { useEffect, useState } from "react";

import { getHealth } from "./api/client";

type Connection =
  | { state: "connecting" }
  | { state: "ready"; version: string }
  | { state: "failed"; message: string };

export function App() {
  const [connection, setConnection] = useState<Connection>({
    state: "connecting",
  });

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (!cancelled) setConnection({ state: "ready", version: health.version });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setConnection({
            state: "failed",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6">
      <h1 className="text-2xl font-semibold tracking-tight">
        Jawut Object Annotation Tools
      </h1>

      {connection.state === "connecting" && (
        <p className="text-ink-muted">Connecting…</p>
      )}

      {connection.state === "ready" && (
        <p className="text-ink-muted">
          Connected — version{" "}
          <span className="font-mono text-ink">{connection.version}</span>
        </p>
      )}

      {connection.state === "failed" && (
        <p className="text-status-review">
          Cannot reach the backend: {connection.message}
        </p>
      )}
    </div>
  );
}
