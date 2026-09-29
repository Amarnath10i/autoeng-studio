"use client";

import { useParams } from "next/navigation";
import { EngineWorkspace } from "@/components/engine/EngineWorkspace";
import { useProject } from "@/components/project/useProject";
import { ErrorNote, Spinner } from "@/components/ui";
import { VehicleWorkspace } from "@/components/vehicle/VehicleWorkspace";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const state = useProject(id);
  if (state.error) return <ErrorNote error={state.error} />;
  if (!state.project || !state.design) return <Spinner label="Loading project…" />;
  return state.project.kind === "vehicle" ? <VehicleWorkspace state={state} /> : <EngineWorkspace state={state} />;
}
