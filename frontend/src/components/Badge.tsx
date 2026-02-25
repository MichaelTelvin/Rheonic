export interface BadgeProps {
  value: string;
  kind?: "status" | "type";
}

export function Badge({ value, kind = "type" }: BadgeProps): JSX.Element {
  const normalized = value.toLowerCase();
  const variant = kind === "status" ? (normalized === "open" ? "warned" : "resolved") : normalized;
  return <span className={`badge ${variant}`}>{normalized}</span>;
}
