import { FormEvent, useRef, useState } from "react";

import { ApiError, login, register, type AuthUser } from "../api/client";

interface LoginProps {
  onAuthSuccess: (user: AuthUser) => void;
}

export function Login({ onAuthSuccess }: LoginProps): JSX.Element {
  const [isRegister, setIsRegister] = useState<boolean>(false);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [emailError, setEmailError] = useState<string>("");
  const [passwordError, setPasswordError] = useState<string>("");
  const [formError, setFormError] = useState<string>("");
  const inputVersionRef = useRef<number>(0);

  const markInputChanged = (): void => {
    inputVersionRef.current += 1;
    setFormError("");
  };

  const onSubmit = async (): Promise<void> => {
    const submitInputVersion = inputVersionRef.current;
    const normalizedEmail = email.trim().toLowerCase();
    const nextEmailError = normalizedEmail ? "" : "Email is required.";
    const nextPasswordError = password ? validatePassword(password, isRegister) : "Password is required.";
    setEmailError(nextEmailError);
    setPasswordError(nextPasswordError);
    setFormError("");
    if (nextEmailError || nextPasswordError) {
      return;
    }
    setBusy(true);
    try {
      if (isRegister) {
        await register(normalizedEmail, password);
      }
      const auth = await login(normalizedEmail, password);
      onAuthSuccess(auth.user);
    } catch (submitError) {
      if (submitInputVersion !== inputVersionRef.current) {
        return;
      }
      if (submitError instanceof ApiError && submitError.status === 409) {
        setFormError("Email already exists.");
      } else if (submitError instanceof ApiError && submitError.status === 400) {
        setFormError(submitError.message);
      } else if (submitError instanceof ApiError && submitError.status === 401) {
        setFormError("Invalid email or password.");
      } else {
        setFormError("Authentication failed.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void onSubmit();
  };

  const passwordMessage = passwordError || formError;

  return (
    <main className="auth-page">
      <section className="auth-card">
        <h1 className="title">{isRegister ? "Create account" : "Sign in"}</h1>
        <form onSubmit={handleSubmit}>
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            className={`text-input ${emailError ? "input-error" : ""}`}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              markInputChanged();
              setEmailError("");
            }}
            placeholder="you@company.com"
          />
          <p className="input-error-slot">{emailError || "\u00A0"}</p>

          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            className={`text-input ${passwordError ? "input-error" : ""}`}
            type="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              markInputChanged();
              setPasswordError("");
            }}
            placeholder={isRegister ? "8+ chars, uppercase, number" : "Your password"}
          />
          <p className="input-error-slot">{passwordMessage || "\u00A0"}</p>

          <div className="auth-actions">
            <button type="submit" className="modal-button modal-primary auth-submit-button" disabled={busy}>
              {isRegister ? "Create account" : "Sign in"}
            </button>
            <button
              type="button"
              className="modal-button"
              onClick={() => {
                setIsRegister((current) => !current);
                setEmailError("");
                setPasswordError("");
                setFormError("");
              }}
              disabled={busy}
            >
              {isRegister ? "Use sign in" : "Create account"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

function validatePassword(password: string, isRegister: boolean): string {
  if (!isRegister) {
    return "";
  }
  if (password.length < 8) {
    return "Password must be at least 8 characters.";
  }
  if (!/[A-Z]/.test(password)) {
    return "Password must include an uppercase letter.";
  }
  if (!/[0-9]/.test(password)) {
    return "Password must include a number.";
  }
  return "";
}
