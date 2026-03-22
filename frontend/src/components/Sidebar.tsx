import { Link, NavLink } from "react-router-dom";

import { RheonicLogoMark } from "./RheonicLogoMark";

interface SidebarProps {
  userEmail: string | null;
  onSignOut: () => void | Promise<void>;
  onSendFeedback: () => void;
}

const navItems = [
  { to: "/app", label: "Dashboard" },
  { to: "/app/projects", label: "Projects" },
  { to: "/app/incidents", label: "Incidents" },
  { to: "/app/settings", label: "Settings" },
  { to: "/app/keys", label: "Keys" },
  { to: "/app/alerts", label: "Alerts" },
  { to: "/app/docs", label: "Docs" },
];

export function Sidebar({ userEmail, onSignOut, onSendFeedback }: SidebarProps): JSX.Element {
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="sidebar-top">
        <Link className="sidebar-brand" to="/" aria-label="Go to Rheonic site">
          <RheonicLogoMark className="brand-logo-icon" />
          <span className="dashboard-brand-word">Rheonic</span>
          <span className="dashboard-beta-badge">BETA</span>
        </Link>
        <div className="sidebar-brand-divider" aria-hidden="true" />
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/app"}
              className={({ isActive }) => `sidebar-link${isActive ? " is-active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="sidebar-bottom">
        <Link className="sidebar-site-link" to="/">
          Visit site
        </Link>
        <button type="button" className="sidebar-feedback-button" onClick={onSendFeedback}>
          <span>Send feedback</span>
        </button>
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
