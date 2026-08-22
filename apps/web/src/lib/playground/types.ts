export type JsonRecord = Record<string, unknown>;

export interface PlaygroundListing extends JsonRecord {
  id: string;
  uuid?: string;
  neighborhood?: string;
  latitude?: number;
  longitude?: number;
}

export interface PlaygroundFixture {
  id: string;
  profile: JsonRecord;
  listings: PlaygroundListing[];
}

export interface ConversationTurnTrace {
  text: string;
  status: string;
  reply?: string | null;
  tool_calls: Array<{ tool: string; status: string }>;
  interrupt?: JsonRecord | null;
  state?: JsonRecord;
}

export interface ConversationTrace {
  fixture_id: string;
  run_id: string;
  turns: ConversationTurnTrace[];
  state_before: JsonRecord;
  state_after: JsonRecord;
  events: JsonRecord[];
  assertions: Array<{ name: string; passed: boolean; value?: unknown }>;
  error?: JsonRecord | null;
}

export interface GeoFeature extends JsonRecord {
  id: string;
  name: string;
  category: string;
  kind: string;
  distance_m?: number | null;
  geometry?: JsonRecord | null;
}

export interface GeoPrimitive extends JsonRecord {
  category: string;
  kind: string;
  feature_ids: string[];
  count_300m: number | null;
  count_600m: number | null;
  nearest_m: number | null;
}

export interface GeoSignal extends JsonRecord {
  signal: string;
  value: number;
  normalized_value: number;
  confidence: number;
  missing: boolean;
  inputs_present: number;
  inputs_total: number;
  contributors: Array<{ term?: string; score?: number; confidence?: number }>;
}

export interface GeoInspection {
  fixture_id: string;
  listing_id: string;
  radius_m: number;
  listing: JsonRecord;
  features: GeoFeature[];
  primitives: GeoPrimitive[];
  signals: GeoSignal[];
  contract_version: string;
  snapshot_id: string;
  attribution: string;
  warnings: string[];
}

