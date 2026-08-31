const TOKEN_KEY = "sde_radar_token";

// "Remember me" is the choice between the two web storages, not a longer
// token: localStorage outlives the browser session, sessionStorage dies with
// the tab. The JWT's own expiry is unchanged either way, so declining to be
// remembered can only shorten how long you stay signed in, never extend it.
export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY) ?? localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string, remember = true) {
  // Always clear both first, so toggling the checkbox between sign-ins can't
  // leave a stale token behind in the store we're no longer writing to.
  clearToken();
  (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
}
/** Whether the current session was "kept signed in".
 *
 * Anything that re-issues a token mid-session -- changing your email or
 * password -- has to write the replacement back to the same store, or the
 * user silently loses (or gains) the choice they made at sign-in.
 */
export function wasRemembered(): boolean {
  return localStorage.getItem(TOKEN_KEY) !== null;
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
  // Only default to JSON when the caller hasn't already said what the body
  // is. FormData and URLSearchParams carry their own encoding -- the login
  // endpoint is an OAuth2 password form, and forcing application/json onto
  // it makes FastAPI reject the request with a 422 that looks, from the UI,
  // like the password was wrong.
  const bodyIsEncoded =
    options.body instanceof FormData || options.body instanceof URLSearchParams;
  if (options.body && !bodyIsEncoded && !headers.has("Content-Type")) {
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
export type WorkMode = "" | "remote" | "hybrid" | "onsite";
export type Seniority = "" | "entry" | "mid" | "senior";

export interface User {
  id: number;
  email: string;
  full_name: string;
  target_cities: string[];
  /** Subdivision codes inside target_country. Empty means every state,
   * which is the default -- it is not the same as "no states". */
  target_states: string[];
  target_titles: string;
  target_country: string;
  work_mode: WorkMode;
  seniority: Seniority;
  min_salary: number | null;
  address: string;
  phone: string;
  has_resume: boolean;
}

export async function register(payload: {
  email: string; password: string; full_name: string; target_city?: string; target_titles?: string;
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

// Returns nothing. The existing token stays valid -- the JWT subject is the
// email, and nothing in the token derives from the password -- so there is no
// credential to hand back and none to store.
export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await request<void>("/auth/password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

// Returns a replacement token: the JWT subject is the email, so the caller's
// current one stops resolving the instant this succeeds.
export async function changeEmail(newEmail: string, currentPassword: string): Promise<{ access_token: string }> {
  return request("/auth/email", {
    method: "POST",
    body: JSON.stringify({ new_email: newEmail, current_password: currentPassword }),
  });
}

export async function fetchMe(): Promise<User> {
  return request("/auth/me");
}

export async function updateMe(
  payload: Partial<Pick<User, "full_name" | "target_cities" | "target_states" | "target_titles" | "target_country" | "work_mode" | "seniority" | "min_salary" | "address" | "phone">>,
): Promise<User> {
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

// ---- Documents ----
export type DocumentKind = "resume" | "cover_letter";

export interface UserDocument {
  id: number;
  kind: DocumentKind;
  label: string;
  filename: string;
  size_bytes: number;
  created_at: string;
}

export async function listDocuments(): Promise<UserDocument[]> {
  return request("/documents");
}

export async function uploadDocument(file: File, kind: DocumentKind, label: string): Promise<UserDocument> {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  form.append("label", label);
  return request("/documents", { method: "POST", body: form });
}

export async function deleteDocument(id: number): Promise<void> {
  await request<void>(`/documents/${id}`, { method: "DELETE" });
}

/** The download endpoint needs the auth header, so it can't be a plain link. */
export async function downloadDocument(doc: UserDocument): Promise<void> {
  const token = getToken();
  const res = await fetch(`/api/documents/${doc.id}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError("Could not download that file.", res.status);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = doc.filename;
  a.click();
  // Revoking immediately can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

// ---- Jobs ----
export type JobStatus = "new" | "saved" | "applied" | "interviewing" | "offer" | "rejected" | "archived";

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
  sources: string[];
  score: number;
  reason: string;
  flag: string | null;
  matches_preferences: boolean;
  mismatch_reason: string | null;
  resume_document_id: number | null;
  cover_letter_document_id: number | null;
  status: JobStatus;
  notes: string;
}

export interface SourceStatus {
  name: string;
  active: boolean;
}

export async function getSources(): Promise<SourceStatus[]> {
  return request<SourceStatus[]>("/sources");
}

export interface Stats {
  total: number;
  avg_score: number;
  applied: number;
  interviewing: number;
  offers: number;
}

export type PostedWithin = "1d" | "7d" | "14d" | "30d";

/** A board in the picker, with how many of its postings are in the window.
 * Derived from the job pool, not the connector registry: a board is offered
 * only when selecting it would show something. */
export interface JobSourceCount {
  name: string;
  count: number;
}

/** `source` narrows to one job board; "all" (or omitted) means every board.
 * An unknown name is a 422 rather than an empty list, so the caller can tell
 * "no such board" apart from "this board is quiet". */
export async function listJobs(postedWithin: PostedWithin = "30d", source?: string): Promise<Job[]> {
  const params = new URLSearchParams({ posted_within: postedWithin });
  if (source) params.set("source", source);
  return request(`/jobs?${params}`);
}

export async function listJobSources(postedWithin: PostedWithin = "30d"): Promise<JobSourceCount[]> {
  return request(`/jobs/sources?posted_within=${postedWithin}`);
}

export async function getStats(): Promise<Stats> {
  return request("/jobs/stats");
}

export async function updateMatch(
  jobId: number,
  payload: {
    status?: JobStatus;
    notes?: string;
    // 0 detaches; omitted leaves the existing link alone.
    resume_document_id?: number;
    cover_letter_document_id?: number;
  },
): Promise<Job> {
  return request(`/jobs/${jobId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function refreshJobs(): Promise<{ added_or_updated: number }> {
  return request("/jobs/refresh", { method: "POST" });
}

// ---- Regions ----
export interface RegionCity {
  name: string;
  job_count: number;
}

export interface Subdivision {
  code: string;
  label: string;
  job_count: number;
  cities: RegionCity[];
}

export interface RegionCountry {
  slug: string;
  label: string;
  /** What this country calls the tier -- State, Province, Land, Nation,
   * County. Used as the picker's own label, because "State" over a list of
   * Canadian provinces reads as a bug to anyone who lives there. */
  subdivision_label: string;
  supports_postal_lookup: boolean;
}

export interface RegionCountryDetail extends RegionCountry {
  subdivisions: Subdivision[];
}

export interface PostalLookup {
  code: string;
  label: string;
  cities: string[];
}

export async function listCountries(): Promise<RegionCountry[]> {
  return request("/regions");
}

export async function getCountry(slug: string): Promise<RegionCountryDetail> {
  return request(`/regions/${encodeURIComponent(slug)}`);
}

/** Resolves a postal code to a subdivision, for the profile address only.
 * Returns null when it can't be placed -- an unsupported country, a
 * malformed code, or a range two subdivisions share. The caller must leave
 * the picker untouched in all three cases rather than guess. */
export async function lookupPostal(country: string, postalCode: string): Promise<PostalLookup | null> {
  try {
    return await request(`/regions/${encodeURIComponent(country)}/postal/${encodeURIComponent(postalCode)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}
