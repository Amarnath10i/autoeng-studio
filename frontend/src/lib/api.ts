// Thin client for the platform API. The session token lives in localStorage.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "autoeng.token";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lasts for this page only */
  }
}

function messageFrom(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((x: unknown) => x !== "body").join(".") : "";
        return loc ? `${loc}: ${d?.msg}` : String(d?.msg ?? d);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return "Request failed";
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const detail = data?.detail ?? data;
    throw new ApiError(res.status, messageFrom(detail), detail);
  }
  return data as T;
}

/** Poll a job until it finishes. */
export async function waitForJob<T = unknown>(
  jobId: string,
  onUpdate?: (status: string) => void,
  signal?: AbortSignal,
): Promise<T> {
  let delay = 400;
  for (;;) {
    if (signal?.aborted) throw new ApiError(0, "Cancelled");
    const job = await api<{ status: string; result: T; error: string | null }>(`/api/v1/jobs/${jobId}`);
    onUpdate?.(job.status);
    if (job.status === "done") return job.result;
    if (job.status === "failed") throw new ApiError(500, job.error ?? "Job failed");
    if (job.status === "cancelled") throw new ApiError(0, "Job cancelled");
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.4, 2500);
  }
}

/** Submit a job to the server or a paired worker and wait for its result. */
export async function runJob<T = unknown>(
  kind: string,
  payload: unknown,
  target = "server",
  onUpdate?: (status: string) => void,
  projectId?: string,
): Promise<T> {
  const job = await api<{ id: string }>("/api/v1/jobs", {
    method: "POST",
    json: { kind, payload, target, project_id: projectId },
  });
  return waitForJob<T>(job.id, onUpdate);
}
