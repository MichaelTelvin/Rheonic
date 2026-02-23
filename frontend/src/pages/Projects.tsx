import { useState } from "react";

import { createProject } from "../api/client";
import { Card } from "../components/Card";
import { FormColumn } from "../components/FormColumn";
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
    } catch (error) {
      setCreateProjectError(error instanceof Error ? error.message : "Failed to create project");
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

        <Card className="form-card card--form">
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

        <Card className="card--table">
          <h2 className="section-title">Project list</h2>
          {projects.length === 0 ? <p className="subtle">No projects yet.</p> : null}
          {projects.length > 0 ? (
            <div className="project-table">
              <div className="project-table-head">
                <span>Name</span>
                <span>ID</span>
                <span>Created</span>
                <span className="table-actions-header">Selection</span>
              </div>
              {projects.map((project) => (
                <div className="project-table-row" key={project.id}>
                  <span className="key-name">{project.name}</span>
                  <span className="subtle mono" title={project.id}>
                    {shortId(project.id)}
                  </span>
                  <span className="subtle">{formatRelative(project.created_at)}</span>
                  <span className="table-actions-cell">
                    <button
                      type="button"
                      className="modal-button action-btn"
                      disabled={project.id === projectId}
                      onClick={() => setProjectId(project.id)}
                    >
                      {project.id === projectId ? "Selected" : "Select"}
                    </button>
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </Card>
      </div>
    </main>
  );
}
