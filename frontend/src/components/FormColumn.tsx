import type { ReactNode } from "react";

interface FormColumnProps {
  children: ReactNode;
  testId?: string;
}

export function FormColumn({ children, testId }: FormColumnProps): JSX.Element {
  return (
    <div className="form-column" data-testid={testId}>
      {children}
    </div>
  );
}
