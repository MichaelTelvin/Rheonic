export interface SparklineProps {
  values: number[];
  stroke: string;
  width?: number;
  height?: number;
}

export function Sparkline({ values, stroke, width = 200, height = 40 }: SparklineProps): JSX.Element {
  const linePath = toSmoothPath(values, width, height);

  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Metric trend">
      <path fill="none" stroke={stroke} strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" d={linePath} />
    </svg>
  );
}

function toSmoothPath(values: number[], width: number, height: number): string {
  if (values.length <= 1) {
    const y = height / 2;
    return `M 0 ${y} L ${width} ${y}`;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const safeRange = range === 0 ? 1 : range;
  const stepX = width / (values.length - 1);

  const points = values.map((value, index) => {
    const x = index * stepX;
    const normalized = range === 0 ? 0.5 : (value - min) / safeRange;
    const y = height - normalized * (height - 4) - 2;
    return { x, y };
  });

  if (points.length === 2) {
    return `M ${points[0].x} ${points[0].y} L ${points[1].x} ${points[1].y}`;
  }

  let path = `M ${points[0].x} ${points[0].y}`;
  // Quadratic midpoint smoothing for visibly curved wave segments.
  for (let index = 1; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    const midX = (current.x + next.x) / 2;
    const midY = (current.y + next.y) / 2;
    path += ` Q ${current.x} ${current.y}, ${midX} ${midY}`;
  }
  const penultimate = points[points.length - 2];
  const last = points[points.length - 1];
  path += ` Q ${penultimate.x} ${penultimate.y}, ${last.x} ${last.y}`;
  return path;
}
