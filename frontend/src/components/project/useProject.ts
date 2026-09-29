"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Json, Project, Version } from "@/lib/types";

/** Project state: branches, history, the head version and a local working copy of its design. */
export function useProject(projectId: string) {
  const [project, setProject] = useState<Project | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [branch, setBranch] = useState<string>("main");
  const [head, setHead] = useState<Version | null>(null);
  const [design, setDesign] = useState<Json | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHead = useCallback(
    async (p: Project, b: string) => {
      const ref = p.branches.find((x) => x.name === b) ?? p.branches[0];
      const v = await api<Version>(`/api/v1/projects/${p.id}/versions/${ref.head_version_id}`);
      setBranch(ref.name);
      setHead(v);
      setDesign(v.design ?? null);
      setDirty(false);
    },
    [],
  );

  const reload = useCallback(
    async (b?: string) => {
      try {
        const [p, vs] = await Promise.all([
          api<Project>(`/api/v1/projects/${projectId}`),
          api<Version[]>(`/api/v1/projects/${projectId}/versions`),
        ]);
        setProject(p);
        setVersions(vs);
        await loadHead(p, b ?? branch);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId, loadHead],
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api<Project>(`/api/v1/projects/${projectId}`),
      api<Version[]>(`/api/v1/projects/${projectId}/versions`),
    ])
      .then(async ([p, vs]) => {
        if (cancelled) return;
        setProject(p);
        setVersions(vs);
        await loadHead(p, p.default_branch);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [projectId, loadHead]);

  const edit = useCallback((next: Json) => {
    setDesign(next);
    setDirty(true);
  }, []);

  const commit = useCallback(
    async (message: string, designOverride?: Json, targetBranch?: string) => {
      if (!project) return;
      const b = targetBranch ?? branch;
      await api<Version>(`/api/v1/projects/${project.id}/commits`, {
        method: "POST",
        json: {
          branch: b,
          message,
          design: designOverride ?? design,
          expected_head: b === branch ? head?.id : undefined,
        },
      });
      await reload(b);
    },
    [project, branch, design, head, reload],
  );

  const discard = useCallback(() => {
    if (head?.design) {
      setDesign(head.design);
      setDirty(false);
    }
  }, [head]);

  const switchBranch = useCallback(
    async (b: string) => {
      if (project) await loadHead(project, b);
    },
    [project, loadHead],
  );

  return { project, versions, branch, head, design, dirty, error, setError, edit, commit, discard, reload, switchBranch };
}

export type ProjectState = ReturnType<typeof useProject>;
