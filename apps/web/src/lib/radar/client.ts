/** Client-side radar API access through the BFF routes. */

export type ProfileStatus = "active" | "paused" | "archived";
export type RunState = "pending" | "running" | "succeeded" | "failed";

export interface RunInfo {
  run_id: string;
  state: RunState;
  trigger: string;
  score_policy_version: string;
  candidate_count: number;
  published_item_count: number;
  failure_code: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface SearchProfile {
  search_profile_id: string;
  name: string;
  operation: string;
  zones: string[];
  budget_max: number;
  budget_min: number | null;
  min_rooms: number;
  surface_min: number | null;
  surface_max: number | null;
  status: ProfileStatus;
  unknown_strategy: Record<string, string>;
  version: number;
  created_at: string;
  updated_at: string;
  latest_run: RunInfo | null;
}

export interface MatchItem {
  item_id: string;
  listing_id: string;
  score: number;
  position: number;
  contributions: Record<string, unknown>;
  geo_precision: string | null;
  geometry: [number, number] | null;
  total_cost: number | null;
  neighborhood: string | null;
  surface_m2: number | null;
  rooms: number | null;
  source_id: string | null;
  url: string | null;
}

export interface MatchesPage {
  search_profile_id: string;
  run_id: string;
  run_state: RunState;
  items: MatchItem[];
  next_after_position: number | null;
}

export interface ListingDetail {
  listing_id: string;
  source_id: string;
  url: string | null;
  neighborhood: string | null;
  geo_precision: string;
  total_cost: number;
  price_value: number;
  price_currency: string;
  expenses_value: number | null;
  surface_m2: number | null;
  rooms: number | null;
  bedrooms: number | null;
  floor: number | null;
  property_type: string;
  amenities: string[];
  description_text: string | null;
  normalization_errors: string[];
  known_changes: Array<{ change_type: string; field: string; before: unknown; after: unknown }>;
}

export interface Problem {
  code: string;
  detail?: string;
  status: number;
}

async function parseResponse(response: Response): Promise<unknown> {
  if (response.ok) return response.json();
  let problem: Problem | null = null;
  try {
    problem = (await response.json()) as Problem;
  } catch {
    problem = null;
  }
  throw new Error(problem?.code ?? `http.${response.status}`);
}

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(path, { headers: { "X-Correlation-ID": crypto.randomUUID() } });
  return parseResponse(response);
}

async function sendJson(path: string, method: string, body: unknown): Promise<unknown> {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", "X-Correlation-ID": crypto.randomUUID() },
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}

export const radarApi = {
  listProfiles: async (status?: ProfileStatus): Promise<SearchProfile[]> =>
    (await getJson(`/api/radar/profiles${status ? `?status=${status}` : ""}`)) as SearchProfile[],
  getProfile: async (id: string): Promise<SearchProfile> =>
    (await getJson(`/api/radar/profiles/${id}`)) as SearchProfile,
  createProfile: async (body: unknown): Promise<SearchProfile> =>
    (await sendJson("/api/radar/profiles", "POST", body)) as SearchProfile,
  updateProfile: async (id: string, expectedVersion: number, changes: unknown): Promise<SearchProfile> =>
    (await sendJson(`/api/radar/profiles/${id}?expected_version=${expectedVersion}`, "PATCH", changes)) as SearchProfile,
  setStatus: async (id: string, expectedVersion: number, status: ProfileStatus): Promise<SearchProfile> =>
    (await sendJson(`/api/radar/profiles/${id}/status?expected_version=${expectedVersion}`, "POST", { status })) as SearchProfile,
  matches: async (id: string, runId: string | null, pageSize: number, afterPosition: number | null): Promise<MatchesPage> => {
    const query = new URLSearchParams({ page_size: String(pageSize) });
    if (runId) query.set("run_id", runId);
    if (afterPosition !== null) query.set("after_position", String(afterPosition));
    return (await getJson(`/api/radar/profiles/${id}/matches?${query.toString()}`)) as MatchesPage;
  },
  listing: async (listingId: string): Promise<ListingDetail> =>
    (await getJson(`/api/radar/listings/${listingId}`)) as ListingDetail,
};
