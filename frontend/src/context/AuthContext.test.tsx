import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthContext, useAuthContext } from "./AuthContext";

function AuthProbe(): JSX.Element {
  const { isAuthenticated, sessionResolved, user } = useAuthContext();
  return (
    <div>
      <span>{isAuthenticated ? "auth" : "guest"}</span>
      <span>{sessionResolved ? "resolved" : "pending"}</span>
      <span>{user?.email ?? "no-user"}</span>
    </div>
  );
}

describe("AuthContext", () => {
  it("returns the current auth context value", () => {
    render(
      <AuthContext.Provider
        value={{
          isAuthenticated: true,
          sessionResolved: true,
          user: { id: "u1", email: "user@example.com", created_at: new Date().toISOString() },
          signOut: () => undefined,
        }}
      >
        <AuthProbe />
      </AuthContext.Provider>,
    );

    expect(screen.getByText("auth")).toBeDefined();
    expect(screen.getByText("resolved")).toBeDefined();
    expect(screen.getByText("user@example.com")).toBeDefined();
  });

  it("throws when used without a provider", () => {
    expect(() => render(<AuthProbe />)).toThrowError("useAuthContext must be used within AuthContext.Provider");
  });
});
