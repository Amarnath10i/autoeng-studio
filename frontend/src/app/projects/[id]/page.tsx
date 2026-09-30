"use client";

import { useParams } from "next/navigation";
import { EngineWorkspace } from "@/components/engine/EngineWorkspace";
import { Container } from "@/components/layout";
import { useProject } from "@/components/project/useProject";
import { ErrorNote, Spinner } from "@/components/ui";
import { VehicleWorkspace } from "@/components/vehicle/VehicleWorkspace";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const state = useProject(id);
  if (state.error)
    return (
      <Container className="py-12">
        <ErrorNote error={state.error} />
      </Container>
    );
  if (!state.project || !state.design)
    return (
      <Container className="py-12">
        <Spinner label="Loading project" />
      </Container>
    );
  return state.project.kind === "vehicle" ? <VehicleWorkspace state={state} /> : <EngineWorkspace state={state} />;
}
