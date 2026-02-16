import type { PropsWithChildren } from "react";

export interface CardProps extends PropsWithChildren {
  className?: string;
}

export function Card({ className, children }: CardProps): JSX.Element {
  return <section className={`card${className ? ` ${className}` : ""}`}>{children}</section>;
}
