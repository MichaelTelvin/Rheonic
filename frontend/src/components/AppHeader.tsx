interface AppHeaderProps {
  userEmail?: string | null;
  onSignOut?: () => void;
}

export function AppHeader({ userEmail = null, onSignOut }: AppHeaderProps): JSX.Element {
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <div className="brand-cluster">
          <p className="subtle top-brand">LLMTokenBurnGuard</p>
        </div>
        <div className="app-header-right">
          {userEmail ? (
            <div className="user-menu">
              <span className="user-chip-email">{userEmail}</span>
              <button type="button" className="modal-button auth-signout" onClick={onSignOut}>
                Sign out
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
