import type { PropsWithChildren } from "react";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";

export function TestRouter({
  children,
  ...props
}: PropsWithChildren<MemoryRouterProps>): JSX.Element {
  return (
    <MemoryRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      {...props}
    >
      {children}
    </MemoryRouter>
  );
}
