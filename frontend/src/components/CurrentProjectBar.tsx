import { useEffect, useState } from "react";

import { fetchProjectProtect } from "../api/client";
import { useProjectContext } from "../context/ProjectContext";

export function CurrentProjectBar(): JSX.Element {
  const { loadingProjects, projectError, projectId, projects, setProjectId } = useProjectContext();
  const [modeLabel, setModeLabel] = useState<string>("Observe");

  useEffect(() => {
    let cancelled = false;

    const loadMode = async (): Promise<void> => {
      if (!projectId) {
        if (!cancelled) {
          setModeLabel("Observe");
        }
        return;
      }
      try {
        const settings = await fetchProjectProtect(projectId);
        if (!cancelled) {
          setModeLabel(settings.protect_enabled ? "Protect" : "Observe");
        }
      } catch {
        if (!cancelled) {
          setModeLabel("Observe");
        }
      }
    };

    void loadMode();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    const onModeUpdated = (event: Event): void => {
      const custom = event as CustomEvent<{ projectId?: string; protect_enabled?: boolean }>;
      if (!custom.detail) {
        return;
      }
      if (projectId && custom.detail.projectId && custom.detail.projectId !== projectId) {
        return;
      }
      if (typeof custom.detail.protect_enabled === "boolean") {
        setModeLabel(custom.detail.protect_enabled ? "Protect" : "Observe");
      }
    };

    window.addEventListener("llmtbg:protect-mode-updated", onModeUpdated as EventListener);
    return () => {
      window.removeEventListener("llmtbg:protect-mode-updated", onModeUpdated as EventListener);
    };
  }, [projectId]);

  return (
    <section className="current-project-bar">
      <div className="current-project-bar-inner">
        <div className="current-project-select-row">
          <label htmlFor="global-project-select">Current project</label>
          <select
            id="global-project-select"
            value={projectId ?? ""}
            onChange={(event) => {
              setProjectId(event.target.value || null);
              event.currentTarget.blur();
            }}
            disabled={loadingProjects || projects.length === 0}
          >
            {projectId ? null : <option value="">Select project</option>}
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <div className="mode-indicator-group">
            <span className="mode-label">Mode</span>
            <span
              className={`mode-indicator ${modeLabel === "Protect" ? "mode-indicator-protect" : "mode-indicator-observe"}`}
              aria-label={`Mode ${modeLabel}`}
              title={`Mode ${modeLabel}`}
            >
              {modeLabel}
            </span>
          </div>
        </div>
        {projectError ? <p className="warning-text">{projectError}</p> : null}
      </div>
    </section>
  );
}
