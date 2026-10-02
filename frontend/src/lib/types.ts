// Shapes of the API's JSON. Designs are kept as plain JSON objects and edited by path.

export type Source =
  | "measured"
  | "manufacturer"
  | "literature"
  | "user"
  | "estimated"
  | "unknown"
  | "calibrated"
  | "community"
  | "calculated"
  | "simulated";

export interface Param {
  value: number;
  source: Source;
  ref?: string | null;
  tol: number;
  dist?: "uniform" | "normal";
}

export type Json = Record<string, unknown>;
export type EngineDesign = Json & { name: string; limits: Limit[] };
export type VehicleDesign = Json & {
  kind: "vehicle";
  name: string;
  components: Record<string, ComponentInstance>;
  connections: { source: string; target: string }[];
  targets: Record<string, number>;
};

export interface ComponentInstance {
  type: string;
  name: string;
  params: Json | null;
  notes?: string;
}

export interface Limit {
  id: string;
  component: string;
  channel: string;
  label?: string | null;
  allowable: Param;
}

export interface ParamSpec {
  path: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  group: string;
  beginner: string;
  engineer: string;
  integer: boolean;
  kind: "param" | "int" | "choice";
  step: number | null;
  choices_from: string | null;
  choices?: { id: string; label: string }[];
  optional: boolean;
}

export interface Channel {
  id: string;
  label: string;
  unit: string;
  description: string;
  digits: number;
}

export interface ComponentInfo {
  id: string;
  name: string;
  system: string;
  channels: string[];
  failure_modes: string[];
  beginner: string;
  params: string[];
}

export interface CatalogType {
  id: string;
  name: string;
  category: string;
  description: string;
  status: "available" | "planned";
  models: string[];
  failure_modes: string[];
  ports: { name: string; kind: string; label: string }[];
  params_schema: Json | null;
  default_params: Json | null;
}

export interface Scenario {
  id?: string;
  name: string;
  description: string;
  weather: { ambient_temp_c: number; altitude_m: number; headwind_kmh: number; surface: "dry" | "wet" | "snow" };
  segments: {
    mode: "cruise" | "full_throttle" | "brake" | "accelerate" | "idle";
    duration_s: number;
    speed_kmh: number;
    rate_g: number;
    grade_pct: number;
  }[];
  repeats: number;
  initial_speed_kmh: number;
  cold_start: boolean;
  dt_s: number;
  duration_s?: number;
}

export interface LibraryItem {
  id: string;
  name: string;
  group?: string;
  summary?: string;
  description?: string;
}

export interface Meta {
  params: ParamSpec[];
  channels: Channel[];
  components: ComponentInfo[];
  edges: { source: string; target: string; kind: string }[];
  model_graph: { id: string; label: string; inputs: string[]; outputs: string[] }[];
  fuels: { id: string; name: string; lhv: Param; afr_stoich: Param; density: Param; notes: string }[];
  sources: Source[];
  status_rules: Record<string, string>;
  calibratable: string[];
  material_properties: Record<string, { label: string; unit: string }>;
  catalog: CatalogType[];
  engine_presets: LibraryItem[];
  vehicle_templates: LibraryItem[];
  engine_preset_groups?: string[];
  vehicle_template_groups?: string[];
  body_styles?: { id: string; name: string; geometry: Json }[];
  material_systems?: Record<string, string>;
  limits: { max_samples: number; default_samples: number };
  sweepable: string[];
  scenarios: Scenario[];
  wind_tunnel?: {
    resolutions: { id: string; cells: number; u: number; re: number; flow_throughs: number }[];
    assumptions: string[];
  };
}

export interface Material {
  id: string;
  name: string;
  category: string;
  condition: string;
  properties: Record<string, Param>;
  processes: string[];
  uses?: string[];
  notes: string;
  custom: boolean;
}

export interface Dist {
  nominal: number;
  p05: number | null;
  p50: number | null;
  p95: number | null;
  rpm?: number;
}

export type Status = "ok" | "warning" | "critical" | "failure" | "no_data" | "unchecked";

export interface LimitResult {
  id: string;
  kind: "limit" | "check";
  component: string;
  label: string;
  unit: string;
  channel: string | null;
  actual_nominal: number | null;
  actual_p95: number | null;
  allowable_nominal: number | null;
  allowable_source: string | null;
  allowable_ref: string | null;
  sf_nominal: number | null;
  sf_p05: number | null;
  p_exceed: number | null;
  at_rpm: number | null;
  status: Status;
  note: string;
}

export interface ChannelResult {
  nominal: (number | null)[];
  p05: (number | null)[];
  p50: (number | null)[];
  p95: (number | null)[];
}

export interface Trust {
  models: { id: string; version: string; fidelity_level: number; name: string }[];
  assumptions: string[] | Record<string, string[]>;
  not_modelled?: string[];
  inputs_by_source?: Record<string, string[]>;
  unknown_inputs?: string[];
  uncertainty?: { method: string; samples: number; seed: number; uncertain_inputs?: string[]; note: string };
  validation?: { status: string; note?: string };
  disclaimer: string;
}

export interface EngineResult {
  design_name: string;
  rpm: number[];
  channels: Record<string, ChannelResult>;
  summary: Record<string, Dist> & { displacement_l: number; specific_power_kw_per_l: number };
  targets: { id: string; channel: string; target: number; nominal: number; probability_met: number; met_nominal: boolean }[];
  limits: LimitResult[];
  component_status: Record<string, Status>;
  status_rules: Record<string, string>;
  material: { id: string; name: string; condition: string; custom: boolean };
  warnings: string[];
  sensitivity: Record<string, { path: string; label: string; rho: number; share: number }[]>;
  trust: Trust;
  compute: { backend: string; device: string };
}

export interface Project {
  id: string;
  name: string;
  description: string;
  kind: "engine" | "vehicle";
  default_branch: string;
  created_at: string;
  updated_at: string;
  branches: { name: string; head_version_id: string }[];
}

export interface Version {
  id: string;
  number: number;
  parent_id: string | null;
  merge_parent_id: string | null;
  branch: string;
  message: string;
  design_hash: string;
  created_at: string;
  name: string;
  design?: Json;
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  target: string;
  error: string | null;
  device: Json;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result?: Json | null;
}

export interface Worker {
  id: string;
  name: string;
  paired: boolean;
  online: boolean;
  device: Json;
  last_seen_at: string | null;
  created_at: string;
}
