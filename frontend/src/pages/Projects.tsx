import { useState } from "react";

import { createProject } from "../api/client";
import { Card } from "../components/Card";
import { FormColumn } from "../components/FormColumn";
import { showAppToast } from "../components/AppToastHost";
import { frontendConfig } from "../config";
import { useProjectContext } from "../context/ProjectContext";
import { formatRelative } from "./dashboardUtils";

const NAME_REGEX = new RegExp(frontendConfig.dashboardNamePattern);
const NAME_MAX = frontendConfig.dashboardNameMaxLength;

export function Projects(): JSX.Element {
  const { projects, projectId, setProjectId, reloadProjects } = useProjectContext();
  const [newProjectName, setNewProjectName] = useState<string>("");
  const [creatingProject, setCreatingProject] = useState<boolean>(false);
  const [createProjectError, setCreateProjectError] = useState<string | null>(null);
  const shortId = (value: string): string => (value.length > 12 ? `${value.slice(0, 6)}...${value.slice(-4)}` : value);
  const backendBaseUrl = frontendConfig.apiBaseUrl.trim();
  const hasBackendBaseUrl = backendBaseUrl.length > 0;

  const onCopyBackendUrl = async (): Promise<void> => {
    if (!hasBackendBaseUrl || !navigator.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(backendBaseUrl);
      showAppToast("URL copied");
    } catch {
      showAppToast("Action failed. Try again");
    }
  };

  const onCopyProjectId = async (value: string): Promise<void> => {
    if (!navigator.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      showAppToast("Project ID copied");
    } catch {
      showAppToast("Action failed. Try again");
    }
  };

  const validateProjectName = (value: string): string | null => {
    if (!value) {
      return "Project name is required.";
    }
    if (value.length > NAME_MAX) {
      return `Project name must be ${NAME_MAX} characters or less.`;
    }
    if (/[\r\n\t]/.test(value)) {
      return "Project name contains invalid characters.";
    }
    if (!NAME_REGEX.test(value)) {
      return "Project name may include letters, numbers, spaces, underscore, dash, and dot.";
    }
    return null;
  };

  const onCreateProject = async (): Promise<void> => {
    const normalized = newProjectName.trim();
    const validationError = validateProjectName(normalized);
    if (validationError) {
      setCreateProjectError(validationError);
      return;
    }
    setCreatingProject(true);
    setCreateProjectError(null);
    try {
      const created = await createProject(normalized);
      const items = await reloadProjects();
      const found = items.find((item) => item.id === created.id);
      setProjectId(found ? found.id : created.id);
      setNewProjectName("");
      showAppToast("Project created");
    } catch (error) {
      setCreateProjectError(error instanceof Error ? error.message : "Failed to create project");
      showAppToast("Action failed. Try again");
    } finally {
      setCreatingProject(false);
    }
  };

  return (
    <main className="dashboard">
      <div className="dashboard-content page-stack">
        <section>
          <h1 className="page-title">Projects</h1>
          <p className="page-subtitle">View and create projects</p>
        </section>

        <section className="projects-top-grid">
          <Card className="form-card card--form projects-create-card">
            <h2 className="section-title">Create project</h2>
            <FormColumn testId="projects-form-column">
              <div className="form-field">
                <label htmlFor="project-name-input">Project name</label>
                <input
                  id="project-name-input"
                  className="text-input"
                  value={newProjectName}
                  onChange={(event) => setNewProjectName(event.target.value)}
                  placeholder="e.g. Prod"
                />
              </div>
              <p className="form-error-slot">{createProjectError ?? "\u00A0"}</p>
              <div className="modal-actions form-actions">
                <button
                  type="button"
                  className="modal-button modal-primary action-btn"
                  onClick={() => void onCreateProject()}
                  disabled={creatingProject}
                >
                  {creatingProject ? "Creating..." : "Create project"}
                </button>
              </div>
            </FormColumn>
          </Card>

          <Card className="form-card projects-integration-card">
            <h2 className="section-title">Integration</h2>
            <div className="projects-integration-body">
              <div className="form-field projects-integration-field">
                <label htmlFor="projects-backend-url">Backend base URL</label>
                <input
                  id="projects-backend-url"
                  className="text-input mono projects-integration-input"
                  readOnly
                  value={hasBackendBaseUrl ? backendBaseUrl : "Not configured"}
                  aria-label="Backend base URL"
                />
              </div>
              <div className="modal-actions form-actions projects-integration-actions">
                <button
                  type="button"
                  className="modal-button modal-primary action-btn"
                  onClick={() => void onCopyBackendUrl()}
                  disabled={!hasBackendBaseUrl}
                >
                  Copy
                </button>
              </div>
            </div>
          </Card>
        </section>

        <Card className="card--table">
          <h2 className="section-title">Project list</h2>
          {projects.length === 0 ? <p className="subtle">No projects yet.</p> : null}
          {projects.length > 0 ? (
            <div className="project-table">
              <div className="project-table-head">
                <span>Name</span>
                <span>ID</span>
                <span>Created</span>
                <span className="table-actions-header">Actions</span>
              </div>
              {projects.map((project) => (
                <div className={`project-table-row${project.id === projectId ? " is-selected" : ""}`} key={project.id}>
                  <span className="key-name">{project.name}</span>
                  <span className="subtle mono" title={project.id}>
                    {shortId(project.id)}
                  </span>
                  <span className="subtle">{formatRelative(project.created_at)}</span>
                  <div className="table-actions-cell project-table-actions">
                    <button
                      type="button"
                      className="table-action-button"
                      onClick={() => void onCopyProjectId(project.id)}
                    >
                      Copy ID
                    </button>
                    <button
                      type="button"
                      className={`table-action-button project-selection-button${project.id === projectId ? " is-selected" : ""}`}
                      onClick={() => setProjectId(project.id)}
                      aria-pressed={project.id === projectId}
                    >
                      {project.id === projectId ? "Selected" : "Select"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </Card>
      </div>
    </main>
  );
}
