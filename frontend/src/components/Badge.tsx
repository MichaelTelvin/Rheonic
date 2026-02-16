export interface BadgeProps {
  severity: string;
}

export function Badge({ severity }: BadgeProps): JSX.Element {
  const normalized = severity.toLowerCase();
  const variant = normalized === "high" || normalized === "medium" ? normalized : "low";
  return <span className={`badge ${variant}`}>{normalized}</span>;
}
