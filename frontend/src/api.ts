const TOKEN_KEY = "sde_radar_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(options.body instanceof FormData) && options.body) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`/api${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---- Auth ----
export interface User {
  id: number;
  email: string;
  full_name: string;
  target_city: string;
  target_titles: string;
  has_resume: boolean;
}

export async function register(payload: {
  email: string; password: string; full_name: string; target_city: string; target_titles: string;
}): Promise<{ access_token: string }> {
  return request("/auth/register", { method: "POST", body: JSON.stringify(payload) });
}

export async function login(email: string, password: string): Promise<{ access_token: string }> {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);
  return request("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
}

export async function fetchMe(): Promise<User> {
  return request("/auth/me");
}

export async function updateMe(payload: Partial<Pick<User, "full_name" | "target_city" | "target_titles">>): Promise<User> {
  return request("/auth/me", { method: "PATCH", body: JSON.stringify(payload) });
}

// ---- Resume ----
export interface Resume {
  filename: string;
  skills: string[];
  years_experience: number | null;
  uploaded_at: string;
}

export async function uploadResume(file: File): Promise<Resume> {
  const form = new FormData();
  form.append("file", file);
  return request("/resume", { method: "POST", body: form });
}

export async function getResume(): Promise<Resume | null> {
  try {
    return await request("/resume");
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

// ---- Jobs ----
export type JobStatus = "new" | "saved" | "applied" | "interviewing" | "offer" | "rejected";

export interface Job {
  id: number;
  title: string;
  company: string;
  location: string;
  comp_min: number | null;
  comp_max: number | null;
  comp_unit: "year" | "hour";
  job_type: string;
  posted: string;
  url: string;
  skills: string[];
  score: number;
  reason: string;
  flag: string | null;
  status: JobStatus;
  notes: string;
}

export interface Stats {
  total: number;
  avg_score: number;
  applied: number;
  interviewing: number;
  offers: number;
}

export async function listJobs(): Promise<Job[]> {
  return request("/jobs");
}

export async function getStats(): Promise<Stats> {
  return request("/jobs/stats");
}

export async function updateMatch(jobId: number, payload: { status?: JobStatus; notes?: string }): Promise<Job> {
  return request(`/jobs/${jobId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function refreshJobs(): Promise<{ added_or_updated: number }> {
  return request("/jobs/refresh", { method: "POST" });
}
