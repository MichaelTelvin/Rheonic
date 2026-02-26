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
      <path fill="none" stroke={stroke} strokeWidth="2.25" d={linePath} />
    </svg>
  );
}

function toSmoothPath(values: number[], width: number, height: number): string {
  if (values.length <= 1) {
    const y = Math.round(height / 2);
    return `M 0 ${y} L ${width} ${y}`;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const safeRange = range === 0 ? 1 : range;
  const stepX = width / (values.length - 1);

  const points = values.map((value, index) => {
    const x = Math.round(index * stepX);
    const normalized = range === 0 ? 0.5 : (value - min) / safeRange;
    const y = Math.round(height - normalized * (height - 4) - 2);
    return { x, y };
  });

  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const curr = points[index];
    const midX = Math.round((prev.x + curr.x) / 2);
    path += ` C ${midX} ${prev.y}, ${midX} ${curr.y}, ${curr.x} ${curr.y}`;
  }
  return path;
}
