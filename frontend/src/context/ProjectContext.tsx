import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { fetchProjects, type ProjectItem } from "../api/client";
import { frontendConfig } from "../config";
import { prefetchProjectWarmState } from "../lib/projectWarmCache";

interface ProjectContextValue {
  loadingProjects: boolean;
  projectError: string | null;
  projects: ProjectItem[];
  projectId: string | null;
  setProjectId: (value: string | null) => void;
  reloadProjects: () => Promise<ProjectItem[]>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }): JSX.Element {
  const [loadingProjects, setLoadingProjects] = useState<boolean>(true);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [projectId, setProjectIdState] = useState<string | null>(() =>
    window.localStorage.getItem(frontendConfig.dashboardSelectedProjectStorageKey),
  );

  const setProjectId = useCallback((value: string | null): void => {
    setProjectIdState(value);
    if (value) {
      window.localStorage.setItem(frontendConfig.dashboardSelectedProjectStorageKey, value);
      return;
    }
    window.localStorage.removeItem(frontendConfig.dashboardSelectedProjectStorageKey);
  }, []);

  const reloadProjects = useCallback(async (): Promise<ProjectItem[]> => {
    const items = await fetchProjects();
    setProjects(items);
    return items;
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadProjects = async (): Promise<void> => {
      try {
        const items = await reloadProjects();
        if (cancelled) {
          return;
        }
        setProjectError(null);
        setProjectIdState((current) => {
          if (current && items.some((item) => item.id === current)) {
            window.localStorage.setItem(frontendConfig.dashboardSelectedProjectStorageKey, current);
            return current;
          }
          if (items.length === 1) {
            window.localStorage.setItem(frontendConfig.dashboardSelectedProjectStorageKey, items[0].id);
            return items[0].id;
          }
          window.localStorage.removeItem(frontendConfig.dashboardSelectedProjectStorageKey);
          return null;
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setProjects([]);
        setProjectIdState(null);
        window.localStorage.removeItem(frontendConfig.dashboardSelectedProjectStorageKey);
        setProjectError(error instanceof Error ? error.message : "Could not load projects from API.");
      } finally {
        if (!cancelled) {
          setLoadingProjects(false);
        }
      }
    };

    void loadProjects();

    return () => {
      cancelled = true;
    };
  }, [reloadProjects]);

  useEffect(() => {
    if (!projectId) {
      return undefined;
    }
    let cancelled = false;

    const warm = async (): Promise<void> => {
      try {
        await prefetchProjectWarmState(projectId);
      } catch {
        if (cancelled) {
          return;
        }
      }
    };

    void warm();
    const interval = window.setInterval(() => {
      void warm();
    }, frontendConfig.dashboardIncidentsPollMs);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId]);

  const value = useMemo<ProjectContextValue>(
    () => ({
      loadingProjects,
      projectError,
      projects,
      projectId,
      setProjectId,
      reloadProjects,
    }),
    [loadingProjects, projectError, projects, projectId, reloadProjects, setProjectId],
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProjectContext(): ProjectContextValue {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error("useProjectContext must be used within ProjectProvider");
  }
  return context;
}
