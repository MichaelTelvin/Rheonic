import { useId } from "react";

interface RheonicLogoMarkProps {
  className?: string;
  title?: string;
}

export function RheonicLogoMark({ className, title = "Rheonic logo" }: RheonicLogoMarkProps): JSX.Element {
  const gradientId = useId();
  return (
    <svg className={className} viewBox="4 16 120 96" role="img" aria-label={title}>
      <defs>
        <linearGradient id={gradientId} x1="4" y1="0" x2="124" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="28%" stopColor="#8d84fc" />
          <stop offset="56%" stopColor="#7a7dff" />
          <stop offset="78%" stopColor="#79a3ff" />
          <stop offset="100%" stopColor="#7cc1ff" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="72" r="8" fill={`url(#${gradientId})`} />
      <path d="M 43 40 Q 36 40 36 47 L 36 89 L 43 100 L 50 89 L 50 47 Q 50 40 43 40 Z" fill={`url(#${gradientId})`} />
      <path d="M 67 22 Q 60 22 60 29 L 60 96 L 67 110 L 74 96 L 74 29 Q 74 22 67 22 Z" fill={`url(#${gradientId})`} />
      <path d="M 91 40 Q 84 40 84 47 L 84 89 L 91 100 L 98 89 L 98 47 Q 98 40 91 40 Z" fill={`url(#${gradientId})`} />
      <path d="M 114 54 Q 107 54 107 61 L 107 82 L 114 92 L 121 82 L 121 61 Q 121 54 114 54 Z" fill={`url(#${gradientId})`} />
    </svg>
  );
}
