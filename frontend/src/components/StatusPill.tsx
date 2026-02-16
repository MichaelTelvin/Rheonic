export interface StatusPillProps {
  connected: boolean;
}

export function StatusPill({ connected }: StatusPillProps): JSX.Element {
  return (
    <span className={`status-pill ${connected ? "connected" : "disconnected"}`}>
      {connected ? "API Connected" : "API Disconnected"}
    </span>
  );
}
