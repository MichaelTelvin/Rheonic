import { useEffect, useRef } from "react";

const IDLE_AMPLITUDE = 0.075;
const WAVE_ANCHOR = 0.76;
const WAVE_SPEED_PER_FRAME = 0.026;
const WAVE_DECAY_PER_FRAME = 0.996;
const MAX_WAVE_AMPLITUDE = 1;

interface WavePulse {
  center: number;
  height: number;
  width: number;
}

export type PulseMeterMode = "requests" | "tokens";

export interface PulseMeterProps {
  values: number[];
  color: string;
  mode?: PulseMeterMode;
  points?: number;
  maxHeight?: number;
}

export function PulseMeter({
  values,
  color,
  mode = "tokens",
  points = 48,
  maxHeight = 54,
}: PulseMeterProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const barsCurrentRef = useRef<number[]>([]);
  const pulsesRef = useRef<WavePulse[]>([]);
  const latestValuesRef = useRef<number[]>(values);
  const previousLastValueRef = useRef<number | null>(null);
  const latestColorRef = useRef<string>(color);
  const latestMaxHeightRef = useRef<number>(maxHeight);
  const latestPointsRef = useRef<number>(Math.max(12, points));

  useEffect(() => {
    latestValuesRef.current = values;
  }, [values]);

  useEffect(() => {
    latestColorRef.current = resolveCanvasColor(color);
  }, [color]);

  useEffect(() => {
    latestMaxHeightRef.current = maxHeight;
  }, [maxHeight]);

  useEffect(() => {
    latestPointsRef.current = Math.max(12, points);
  }, [points]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return undefined;
    }
    const parent = canvas.parentElement;
    if (!parent) {
      return undefined;
    }

    const ensureBuffers = (): void => {
      const pointCount = latestPointsRef.current;
      if (barsCurrentRef.current.length !== pointCount) {
        barsCurrentRef.current = new Array(pointCount).fill(IDLE_AMPLITUDE);
        pulsesRef.current = [];
      }
    };

    const resize = (): void => {
      const dpr = Math.max(1, window.devicePixelRatio || 1);
      const rect = parent.getBoundingClientRect();
      const width = Math.max(1, Math.floor(rect.width));
      const height = Math.max(1, Math.floor(rect.height));
      const nextW = Math.floor(width * dpr);
      const nextH = Math.floor(height * dpr);
      if (canvas.width !== nextW || canvas.height !== nextH) {
        canvas.width = nextW;
        canvas.height = nextH;
      }
    };

    const maybeInjectPulse = (): void => {
      const nextValues = latestValuesRef.current;
      if (nextValues.length === 0) {
        return;
      }
      const newest = toSafe(nextValues[nextValues.length - 1]);
      const previousLast = previousLastValueRef.current;
      previousLastValueRef.current = newest;
      if (previousLast === null) {
        return;
      }
      const delta = newest - previousLast;
      if (delta <= 0.0001) {
        return;
      }

      ensureBuffers();
      const recent = nextValues.slice(-Math.max(2, Math.min(24, nextValues.length))).map(toSafe);
      const recentMax = Math.max(1, ...recent);
      const energy = clamp(Math.log1p(delta) / Math.log1p(recentMax), 0, 1);
      if (energy < 0.02) {
        return;
      }

      const pointCount = barsCurrentRef.current.length;
      if (pointCount === 0) {
        return;
      }

      const baseCenter = (pointCount - 1) * WAVE_ANCHOR;
      if (mode === "requests") {
        const requestEnergy = clamp(delta / Math.max(1, recentMax * 0.35), 0, 1);
        const height = 0.1 + requestEnergy * 0.32;
        const width = 0.78 + requestEnergy * 0.62;
        pulsesRef.current.push({
          center: baseCenter,
          height: clamp(height, 0.08, 0.56),
          width,
        });
      } else {
        const tokenEnergy = clamp(Math.log1p(delta) / 7.4, 0, 1);
        const height = 0.1 + tokenEnergy * 0.48;
        const width = 0.8 + tokenEnergy * 1;
        pulsesRef.current.push({ center: baseCenter, height, width });
      }

      if (pulsesRef.current.length > 36) {
        pulsesRef.current.splice(0, pulsesRef.current.length - 36);
      }
    };

    const draw = (): void => {
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        return;
      }
      const dpr = Math.max(1, window.devicePixelRatio || 1);
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;
      const baselineY = height - 1;
      const bars = barsCurrentRef.current;
      if (bars.length === 0) {
        ctx.clearRect(0, 0, width, height);
        return;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      ctx.save();
      ctx.strokeStyle = "rgba(229, 231, 235, 0.1)";
      ctx.lineWidth = 1;
      ctx.setLineDash([1, 3]);
      ctx.beginPath();
      ctx.moveTo(0, baselineY);
      ctx.lineTo(width, baselineY);
      ctx.stroke();
      ctx.restore();

      const step = width / bars.length;
      const barWidth = Math.max(2, Math.min(4, step * 0.62));
      const maxBarHeight = Math.max(10, Math.min(height - 5, latestMaxHeightRef.current));
      const resolvedColor = latestColorRef.current;

      const drawRoundedBar = (x: number, h: number): void => {
        const top = baselineY - h;
        const radius = Math.min(2.5, barWidth / 2, h / 2);
        ctx.beginPath();
        ctx.moveTo(x, baselineY);
        ctx.lineTo(x, top + radius);
        ctx.quadraticCurveTo(x, top, x + radius, top);
        ctx.lineTo(x + barWidth - radius, top);
        ctx.quadraticCurveTo(x + barWidth, top, x + barWidth, top + radius);
        ctx.lineTo(x + barWidth, baselineY);
        ctx.closePath();
        ctx.fill();
      };

      ctx.save();
      ctx.fillStyle = resolvedColor;
      ctx.shadowColor = resolvedColor;
      ctx.shadowBlur = 4;
      ctx.globalAlpha = 0.62;
      for (let index = 0; index < bars.length; index += 1) {
        const amplitude = clamp(bars[index], IDLE_AMPLITUDE, MAX_WAVE_AMPLITUDE);
        const h = amplitude * maxBarHeight;
        const x = index * step + (step - barWidth) / 2;
        drawRoundedBar(x, h);
      }
      ctx.restore();
    };

    const tick = (): void => {
      ensureBuffers();
      resize();
      maybeInjectPulse();

      const barsCurrent = barsCurrentRef.current;
      const activePulses = pulsesRef.current;

      for (let pulseIndex = activePulses.length - 1; pulseIndex >= 0; pulseIndex -= 1) {
        const pulse = activePulses[pulseIndex];
        pulse.center -= WAVE_SPEED_PER_FRAME;
        pulse.height *= WAVE_DECAY_PER_FRAME;
        if (pulse.height < 0.0025 || pulse.center < -8) {
          activePulses.splice(pulseIndex, 1);
        }
      }

      for (let index = 0; index < barsCurrent.length; index += 1) {
        let amplitude = IDLE_AMPLITUDE;
        for (let pulseIndex = 0; pulseIndex < activePulses.length; pulseIndex += 1) {
          const pulse = activePulses[pulseIndex];
          const distance = (index - pulse.center) / pulse.width;
          amplitude += pulse.height * Math.exp(-0.5 * distance * distance);
        }
        barsCurrent[index] = clamp(amplitude, IDLE_AMPLITUDE, MAX_WAVE_AMPLITUDE);
      }

      draw();
      rafRef.current = window.requestAnimationFrame(tick);
    };

    const onResize = (): void => resize();
    window.addEventListener("resize", onResize);
    const resizeObserver =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => resize())
        : null;
    resizeObserver?.observe(parent);

    ensureBuffers();
    resize();
    rafRef.current = window.requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("resize", onResize);
      resizeObserver?.disconnect();
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current);
      }
      rafRef.current = null;
    };
  }, []);

  return (
    <div className={`pulse-meter pulse-meter--${mode}`} role="img" aria-label="Metric pulse meter">
      <canvas ref={canvasRef} aria-hidden="true" />
    </div>
  );
}

function toSafe(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function resolveCanvasColor(raw: string): string {
  const trimmed = raw.trim();
  if (typeof window === "undefined" || !trimmed.startsWith("var(")) {
    return trimmed || "#93c5fd";
  }
  const match = trimmed.match(/^var\(\s*(--[^,\s)]+).*?\)$/);
  const varName = match?.[1];
  if (!varName) {
    return trimmed || "#93c5fd";
  }
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return value || "#93c5fd";
}
