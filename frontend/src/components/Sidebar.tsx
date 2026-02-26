import { NavLink } from "react-router-dom";

interface SidebarProps {
  userEmail: string | null;
  onSignOut: () => void;
}

const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/projects", label: "Projects" },
  { to: "/incidents", label: "Incidents" },
  { to: "/settings", label: "Settings" },
  { to: "/keys", label: "Keys" },
  { to: "/alerts", label: "Alerts" },
  { to: "/docs", label: "Docs" },
];

export function Sidebar({ userEmail, onSignOut }: SidebarProps): JSX.Element {
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="sidebar-top">
        <p className="sidebar-brand">LLMTokenBurnGuard</p>
        <div className="sidebar-brand-divider" aria-hidden="true" />
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `sidebar-link${isActive ? " is-active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="sidebar-bottom">
        <div className="sidebar-footer-divider" aria-hidden="true" />
        <div className="sidebar-user-row">
          <p className="sidebar-user-email" title={userEmail ?? "Unknown user"}>
            {userEmail ?? "Unknown user"}
          </p>
          <button type="button" className="modal-button auth-signout" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </div>
    </aside>
  );
}
