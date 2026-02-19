import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { Login } from "./Login";

const mockLogin = vi.fn();
const mockRegister = vi.fn();

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    login: (...args: unknown[]) => mockLogin(...args),
    register: (...args: unknown[]) => mockRegister(...args),
  };
});

describe("Login", () => {
  beforeEach(() => {
    mockLogin.mockReset();
    mockRegister.mockReset();
  });

  it("shows required field errors on empty submit", async () => {
    render(<Login onAuthSuccess={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Email is required.")).toBeDefined();
    expect(screen.getByText("Password is required.")).toBeDefined();
  });

  it("clears only the edited field error", async () => {
    const user = userEvent.setup();
    render(<Login onAuthSuccess={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const emailInput = screen.getByLabelText("Email");
    await user.type(emailInput, "test@example.com");
    await waitFor(() => {
      expect(screen.queryByText("Email is required.")).toBeNull();
    });
    expect(screen.getByText("Password is required.")).toBeDefined();
  });

  it("submits login with normalized email", async () => {
    const user = userEvent.setup();
    const onAuthSuccess = vi.fn();
    mockLogin.mockResolvedValue({
      access_token: "token",
      token_type: "bearer",
      user: { id: "u1", email: "test@example.com", created_at: new Date().toISOString() },
    });

    render(<Login onAuthSuccess={onAuthSuccess} />);
    await user.type(screen.getByLabelText("Email"), "  TEST@Example.com ");
    await user.type(screen.getByLabelText("Password"), "password123");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("test@example.com", "password123");
      expect(onAuthSuccess).toHaveBeenCalled();
    });
  });

  it("register mode calls register then login", async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValue({ id: "u1", email: "new@example.com", created_at: new Date().toISOString() });
    mockLogin.mockResolvedValue({
      access_token: "token",
      token_type: "bearer",
      user: { id: "u1", email: "new@example.com", created_at: new Date().toISOString() },
    });

    render(<Login onAuthSuccess={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith("new@example.com", "password123");
      expect(mockLogin).toHaveBeenCalledWith("new@example.com", "password123");
    });
  });

  it("maps API errors to user-friendly form messages", async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValue(new ApiError(401, "bad creds"));
    render(<Login onAuthSuccess={vi.fn()} />);
    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Invalid email or password.")).toBeDefined();
  });

  it("submits form on Enter key", async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValue({
      access_token: "token",
      token_type: "bearer",
      user: { id: "u1", email: "enter@example.com", created_at: new Date().toISOString() },
    });
    render(<Login onAuthSuccess={vi.fn()} />);
    await user.type(screen.getByLabelText("Email"), "enter@example.com");
    await user.type(screen.getByLabelText("Password"), "password123{enter}");
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalled();
    });
  });
});
