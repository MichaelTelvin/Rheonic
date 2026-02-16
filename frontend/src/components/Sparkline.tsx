export interface SparklineProps {
  values: number[];
  stroke: string;
  width?: number;
  height?: number;
}

export function Sparkline({ values, stroke, width = 200, height = 40 }: SparklineProps): JSX.Element {
  const linePoints = toPoints(values, width, height);

  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Metric trend">
      <polyline fill="none" stroke={stroke} strokeWidth="2.25" points={linePoints} />
    </svg>
  );
}

function toPoints(values: number[], width: number, height: number): string {
  if (values.length <= 1) {
    const y = Math.round(height / 2);
    return `0,${y} ${width},${y}`;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const safeRange = range === 0 ? 1 : range;
  const stepX = width / (values.length - 1);

  return values
    .map((value, index) => {
      const x = Math.round(index * stepX);
      const normalized = range === 0 ? 0.5 : (value - min) / safeRange;
      const y = Math.round(height - normalized * (height - 4) - 2);
      return `${x},${y}`;
    })
    .join(" ");
}
