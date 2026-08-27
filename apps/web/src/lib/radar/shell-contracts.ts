export type Radar = {
  search_profile_id: string;
  name: string;
  status: "active" | "paused" | "archived";
  zones: string[];
  budget_max: number;
  min_rooms: number | null;
};

export type Oportunidad = {
  listing_id: string;
  latitude: number | null;
  longitude: number | null;
  neighborhood: string | null;
  total_cost: number | null;
  surface_m2: number | null;
  rooms: number | null;
  source_id: string | null;
  score: number;
  reasons: { criterion_key: string; text: string; evidence_level: "strong" | "medium" | "low" }[];
  missing_data: string[];
  confidence: number;
  score_version: string;
  decision_state: string | null;
  urban_signals?: Record<string, { count_300m: number; count_600m: number; distance_nearest: number | null }>;
  snapshot?: { date: string; sha256: string };
};

export type PinState = "default" | "hover" | "selected";

export type Viewport = {
  center: [number, number];
  zoom: number;
  reason: string;
  animated: boolean;
};

export type ListFilter = "all" | "saved" | "dismissed";
