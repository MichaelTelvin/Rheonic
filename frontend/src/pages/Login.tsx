import { useState } from "react";

import { ApiError, login, register, type LoginResponse } from "../api/client";

interface LoginProps {
  onAuthSuccess: (auth: LoginResponse) => void;
}

export function Login({ onAuthSuccess }: LoginProps): JSX.Element {
  const [isRegister, setIsRegister] = useState<boolean>(false);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [emailError, setEmailError] = useState<string>("");
  const [passwordError, setPasswordError] = useState<string>("");
  const [formError, setFormError] = useState<string>("");

  const onSubmit = async (): Promise<void> => {
    const normalizedEmail = email.trim().toLowerCase();
    const nextEmailError = normalizedEmail ? "" : "Email is required.";
    const nextPasswordError = password ? "" : "Password is required.";
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
      onAuthSuccess(auth);
    } catch (submitError) {
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

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-card-head">
          <h1 className="title">{isRegister ? "Create account" : "Sign in"}</h1>
          <p className="subtle auth-brand">
            <svg className="auth-brand-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 2.2 4.5 5.2v6.6c0 4.8 3.1 9.1 7.5 10.6 4.4-1.5 7.5-5.8 7.5-10.6V5.2L12 2.2Z" />
              <path d="M12 4.6 6.8 6.7v5.1c0 3.4 2 6.5 5.2 7.9 3.2-1.4 5.2-4.5 5.2-7.9V6.7L12 4.6Z" className="auth-brand-icon-cutout" />
            </svg>
            <span>LLMTokenBurnGuard</span>
          </p>
        </div>

        <label htmlFor="login-email">Email</label>
        <input
          id="login-email"
          className={`text-input ${emailError ? "input-error" : ""}`}
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
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
          onChange={(event) => setPassword(event.target.value)}
          placeholder="At least 8 characters"
        />
        <p className="input-error-slot">{passwordError || "\u00A0"}</p>
        <p className="input-error-slot">{formError || "\u00A0"}</p>

        <div className="auth-actions">
          <button type="button" className="modal-button modal-primary" onClick={() => void onSubmit()} disabled={busy}>
            {busy ? "Please wait..." : isRegister ? "Create account" : "Sign in"}
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
      </section>
    </main>
  );
}
