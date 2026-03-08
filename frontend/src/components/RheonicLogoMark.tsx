import { useId } from "react";

interface RheonicLogoMarkProps {
  className?: string;
  title?: string;
}

export function RheonicLogoMark({ className, title = "Rheonic logo" }: RheonicLogoMarkProps): JSX.Element {
  const gradientId = useId();
  return (
    <svg className={className} viewBox="0 0 256 256" role="img" aria-label={title}>
      <defs>
        <linearGradient id={gradientId} x1="44" y1="128" x2="212" y2="128" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="45%" stopColor="#7a7dff" />
          <stop offset="100%" stopColor="#7cc1ff" />
        </linearGradient>
        <filter id={`${gradientId}-glow`} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect x="39" y="39" width="178" height="178" rx="0" fill="none" stroke={`url(#${gradientId})`} strokeWidth="22" />
      <g filter={`url(#${gradientId}-glow)`} fill="none" stroke={`url(#${gradientId})`} strokeWidth="12" strokeLinecap="round">
        <path d="M 46 128 L 99 128" />
        <path d="M 157 128 L 210 128" />
        <circle cx="128" cy="128" r="31" />
      </g>
    </svg>
  );
}
