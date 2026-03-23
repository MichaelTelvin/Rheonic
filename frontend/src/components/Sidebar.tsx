import { Link, NavLink } from "react-router-dom";

import { RheonicLogoMark } from "./RheonicLogoMark";

interface SidebarProps {
  userEmail: string | null;
  onSignOut: () => void | Promise<void>;
  onSendFeedback: () => void;
}

type NavIconProps = {
  title: string;
};

function iconProps(title: string): JSX.IntrinsicElements["svg"] {
  return {
    "aria-hidden": "true",
    focusable: "false",
    viewBox: "0 0 24 24",
    width: 18,
    height: 18,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      flex: "0 0 auto",
      display: "block",
      color: "rgba(245, 247, 255, 0.94)",
      opacity: 0.98,
    },
    role: "img",
  };
}

function DashboardIcon({ title }: NavIconProps): JSX.Element {
  return (
    <svg {...iconProps(title)}>
      <rect x="4.5" y="11" width="3" height="7.5" rx="0.9" />
      <rect x="10.5" y="7.5" width="3" height="11" rx="0.9" />
      <rect x="16.5" y="4.5" width="3" height="14" rx="0.9" />
    </svg>
  );
}

function ProjectsIcon({ title }: NavIconProps): JSX.Element {
  return (
    <svg {...iconProps(title)}>
      <path d="M8.25 4.25H6.75a2.5 2.5 0 0 0-2.5 2.5v1.5" />
      <path d="M15.75 4.25h1.5a2.5 2.5 0 0 1 2.5 2.5v1.5" />
      <path d="M8.25 19.75h-1.5a2.5 2.5 0 0 1-2.5-2.5v-1.5" />
      <path d="M15.75 19.75h1.5a2.5 2.5 0 0 0 2.5-2.5v-1.5" />
      <rect x="7.25" y="7.25" width="9.5" height="9.5" rx="2.1" />
      <path d="M12 7.25v-3" />
      <path d="M12 19.75v-3" />
      <path d="M7.25 12h-3" />
      <path d="M19.75 12h-3" />
    </svg>
  );
}

function IncidentsIcon({ title }: NavIconProps): JSX.Element {
  return (
    <svg {...iconProps(title)}>
      <rect x="4" y="6.5" width="16" height="8.5" rx="1.9" />
      <path d="M6 18h12" />
      <path d="M6 3.75h12" />
    </svg>
  );
}

function SettingsIcon({ title }: NavIconProps): JSX.Element {
  return (
    <svg {...iconProps(title)}>
      <path d="M4 7h8" />
      <circle cx="15.75" cy="7" r="2.25" />
      <path d="M18 7h2" />
      <path d="M4 17h2" />
      <circle cx="8.25" cy="17" r="2.25" />
      <path d="M10.5 17H20" />
    </svg>
  );
}

function KeysIcon({ title }: NavIconProps): JSX.Element {
  return (
    <svg {...iconProps(title)}>
      <path d="M7.25 10.25V8.5a4.75 4.75 0 0 1 9.5 0v1.75" />
      <rect x="5" y="10.25" width="14" height="10.5" rx="2.1" />
      <path d="M12 14v3" />
      <circle cx="12" cy="14" r="0.15" fill="currentColor" stroke="none" />
    </svg>
  );
}

function AlertsIcon({ title }: NavIconProps): JSX.Element {
  return (
    <svg {...iconProps(title)}>
      <path d="M12 9v4" />
      <path d="M12 16h.01" />
      <path d="M10.363 3.591 2.257 17.125A1.914 1.914 0 0 0 3.893 20h16.214a1.914 1.914 0 0 0 1.636-2.87L13.637 3.59a1.914 1.914 0 0 0-3.274 0" />
    </svg>
  );
}

function DocsIcon({ title }: NavIconProps): JSX.Element {
  return (
    <svg {...iconProps(title)}>
      <path d="M6 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1" />
      <path d="M9 4v16" />
      <path d="M13 8h2" />
      <path d="M13 12h2" />
    </svg>
  );
}

function SiteIcon({ title }: NavIconProps): JSX.Element {
  return (
    <svg {...iconProps(title)}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17" />
      <path d="M12 3.5c2.2 2.7 3.5 5.6 3.5 8.5s-1.3 5.8-3.5 8.5" />
      <path d="M12 3.5c-2.2 2.7-3.5 5.6-3.5 8.5s1.3 5.8 3.5 8.5" />
    </svg>
  );
}

const navItems = [
  { to: "/app", label: "Dashboard", Icon: DashboardIcon },
  { to: "/app/projects", label: "Projects", Icon: ProjectsIcon },
  { to: "/app/incidents", label: "Incidents", Icon: IncidentsIcon },
  { to: "/app/settings", label: "Settings", Icon: SettingsIcon },
  { to: "/app/keys", label: "Keys", Icon: KeysIcon },
  { to: "/app/alerts", label: "Alerts", Icon: AlertsIcon },
  { to: "/app/docs", label: "Docs", Icon: DocsIcon },
  { to: "/", label: "Site", Icon: SiteIcon },
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
              <item.Icon title={item.label} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="sidebar-bottom">
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
