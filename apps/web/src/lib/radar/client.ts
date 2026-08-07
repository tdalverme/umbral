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
  decision_state?: FeedbackEventType | null;
}

export interface MatchesPage {
  search_profile_id: string;
  run_id: string;
  run_state: RunState;
  items: MatchItem[];
  next_after_position: number | null;
}

export type FeedbackEventType = "like" | "dislike" | "save" | "dismiss" | "contacted";
export type ProposalState = "pending" | "confirmed" | "rejected" | "expired" | "superseded";

export interface FeedbackRecord {
  event_id: string;
  search_profile_id: string;
  listing_id: string;
  event_type: FeedbackEventType;
  decision_state: FeedbackEventType;
  superseded: boolean;
  noop: boolean;
  reason_keys: string[];
}

export interface DecisionItem {
  listing_id: string;
  decision_state: FeedbackEventType;
  event_id: string;
  event_type: FeedbackEventType;
  reason_keys: string[];
  created_at: string;
  total_cost: number | null;
  neighborhood: string | null;
  surface_m2: number | null;
  rooms: number | null;
  source_id: string | null;
  url: string | null;
  geo_precision: string | null;
}

export interface DecisionItemsPage {
  search_profile_id: string;
  items: DecisionItem[];
  next_after_position: number | null;
}

export interface Proposal {
  proposal_id: string;
  search_profile_id: string;
  concept_key: string;
  policy_version: string;
  change: {
    kind: string;
    concept_key: string;
    polarity: string;
    suggested_weight: number;
    suggested_confidence: number;
    value: unknown;
  };
  evidence_refs: Array<Record<string, string>>;
  state: ProposalState;
  expires_at: string;
  created_at: string;
}

export interface ProposalsPage {
  search_profile_id: string;
  items: Proposal[];
  next_after_position: number | null;
}

export interface Confirmation {
  proposal: Proposal;
  applied_profile_version: number;
  run_id: string | null;
}

export interface ListingChange {
  change_type: string;
  field: string;
  before: unknown;
  after: unknown;
  source?: string | null;
  observed_at?: string | null;
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
  known_changes: ListingChange[];
}

export interface Problem {
  code: string;
  detail?: string;
  status: number;
}

export interface ExplanationReason {
  criterion_key: string;
  state: "match" | "mismatch" | "unknown";
  score: number;
  confidence: number;
  contribution: number;
  evidence_level: "strong" | "medium" | "low";
  reason_code: string;
  evidence_refs: Array<Record<string, string>>;
  text: string;
}

export interface ExplanationRisk {
  criterion_key: string;
  state: "match" | "mismatch" | "unknown";
  reason_code: string;
  text: string;
}

export interface Explanation {
  search_profile_id: string;
  run_id: string;
  listing_id: string;
  score_version: string;
  score: number;
  confidence: number;
  reasons: ExplanationReason[];
  risks: ExplanationRisk[];
  missing_data: string[];
  satisfied_filters: string[];
  profile_snapshot: Record<string, string>;
  feature_snapshot: Record<string, string>;
}

export interface ExplanationsPage {
  search_profile_id: string;
  run_id: string;
  run_state: RunState;
  items: Explanation[];
  next_after_position: number | null;
}

export interface ComparisonCell {
  listing_id: string;
  dimension_key: string;
  value: unknown;
  state: "match" | "mismatch" | "unknown";
  missing: boolean;
  evidence_refs: Array<Record<string, string>>;
}

export interface Comparison {
  search_profile_id: string;
  run_id: string;
  score_version: string;
  limit: number;
  listings: Array<{ listing_id: string; position: number }>;
  dimensions: Array<{ kind: "fixed" | "criterion"; key: string; label: string; concept: string | null }>;
  cells: ComparisonCell[];
}

export interface Shortlist {
  search_profile_id: string;
  listing_ids: string[];
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
  matches: async (id: string, runId: string | null, pageSize: number, afterPosition: number | null, includeDismissed = false): Promise<MatchesPage> => {
    const query = new URLSearchParams({ page_size: String(pageSize) });
    if (runId) query.set("run_id", runId);
    if (afterPosition !== null) query.set("after_position", String(afterPosition));
    if (includeDismissed) query.set("include_dismissed", "true");
    return (await getJson(`/api/radar/profiles/${id}/matches?${query.toString()}`)) as MatchesPage;
  },
  listing: async (listingId: string): Promise<ListingDetail> =>
    (await getJson(`/api/radar/listings/${listingId}`)) as ListingDetail,
  explanations: async (
    id: string,
    runId: string | null,
    pageSize: number,
    afterPosition: number | null,
  ): Promise<ExplanationsPage> => {
    const query = new URLSearchParams({ page_size: String(pageSize) });
    if (runId) query.set("run_id", runId);
    if (afterPosition !== null) query.set("after_position", String(afterPosition));
    return (await getJson(`/api/radar/profiles/${id}/explanations?${query.toString()}`)) as ExplanationsPage;
  },
  explanation: async (id: string, listingId: string, runId: string | null): Promise<Explanation> => {
    const query = new URLSearchParams();
    if (runId) query.set("run_id", runId);
    const suffix = query.toString();
    return (await getJson(
      `/api/radar/profiles/${id}/explanations/${listingId}${suffix ? `?${suffix}` : ""}`,
    )) as Explanation;
  },
  comparison: async (id: string, listingIds: string[]): Promise<Comparison> =>
    (await sendJson(`/api/radar/profiles/${id}/comparisons`, "POST", { listing_ids: listingIds })) as Comparison,
  getShortlist: async (id: string): Promise<Shortlist> =>
    (await getJson(`/api/radar/profiles/${id}/comparison-shortlist`)) as Shortlist,
  setShortlist: async (id: string, listingIds: string[]): Promise<Shortlist> =>
    (await sendJson(`/api/radar/profiles/${id}/comparison-shortlist`, "PUT", {
      listing_ids: listingIds,
    })) as Shortlist,
  recordFeedback: async (
    id: string,
    body: {
      listing_id: string;
      run_id?: string | null;
      event_type: FeedbackEventType;
      reason_keys: string[];
      idempotency_key: string;
      free_feedback?: string | null;
    },
  ): Promise<FeedbackRecord> =>
    (await sendJson(`/api/radar/profiles/${id}/feedback`, "POST", body)) as FeedbackRecord,
  decisionItems: async (
    id: string,
    decisionState: FeedbackEventType,
    pageSize = 100,
    afterPosition: number | null = null,
  ): Promise<DecisionItemsPage> => {
    const query = new URLSearchParams({ page_size: String(pageSize), decision_state: decisionState });
    if (afterPosition !== null) query.set("after_position", String(afterPosition));
    return (await getJson(`/api/radar/profiles/${id}/decision-items?${query.toString()}`)) as DecisionItemsPage;
  },
  listProposals: async (id: string, state: ProposalState | null = "pending"): Promise<ProposalsPage> => {
    const query = new URLSearchParams();
    if (state) query.set("state", state);
    return (await getJson(`/api/radar/profiles/${id}/learning-proposals?${query.toString()}`)) as ProposalsPage;
  },
  expandProposal: async (id: string, proposalId: string, change: Proposal["change"]): Promise<Proposal> =>
    (await sendJson(`/api/radar/profiles/${id}/learning-proposals/${proposalId}`, "PUT", { change })) as Proposal,
  confirmProposal: async (id: string, proposalId: string): Promise<Confirmation> =>
    (await sendJson(`/api/radar/profiles/${id}/learning-proposals/${proposalId}/confirm`, "POST", {})) as Confirmation,
  rejectProposal: async (id: string, proposalId: string): Promise<Proposal> =>
    (await sendJson(`/api/radar/profiles/${id}/learning-proposals/${proposalId}/reject`, "POST", {})) as Proposal,
  undoProposal: async (id: string, proposalId: string): Promise<Proposal> =>
    (await sendJson(`/api/radar/profiles/${id}/learning-proposals/${proposalId}/undo`, "POST", {})) as Proposal,
};
