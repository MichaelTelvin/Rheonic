import { useId, useState } from "react";

interface InfoTooltipProps {
  text: string;
}

export function InfoTooltip({ text }: InfoTooltipProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const tooltipId = useId();

  return (
    <span className="info-tooltip-wrap">
      <button
        type="button"
        className="info-tooltip-trigger"
        aria-label="More info"
        aria-describedby={open ? tooltipId : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        i
      </button>
      {open ? (
        <span id={tooltipId} role="tooltip" className="info-tooltip-panel">
          {text}
        </span>
      ) : null}
    </span>
  );
}
