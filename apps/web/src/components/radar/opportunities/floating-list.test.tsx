import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FloatingList } from "./floating-list";
import type { Explanation, MatchItem } from "@/lib/radar/client";

const opportunity: MatchItem = {
  item_id: "item-1",
  listing_id: "listing-1",
  score: 0.8,
  position: 1,
  contributions: {},
  geo_precision: null,
  geometry: null,
  total_cost: 207000,
  neighborhood: "palermo",
  surface_m2: 54,
  rooms: 2,
  source_id: null,
  url: null,
};

const explanation: Explanation = {
  search_profile_id: "profile-1",
  run_id: "run-1",
  listing_id: "listing-1",
  score_version: "scoring-v1",
  score: 0.8,
  confidence: 0.9,
  reasons: [{
    criterion_key: "luminosidad",
    state: "match",
    score: 1,
    confidence: 0.9,
    contribution: 0.2,
    evidence_level: "strong",
    reason_code: "concept_observed",
    evidence_refs: [],
    text: "El aviso sugiere buena luz natural.",
  }],
  risks: [],
  missing_data: [],
  satisfied_filters: [],
  profile_snapshot: {},
  feature_snapshot: {},
};

describe("FloatingList", () => {
  it("muestra una razón breve sin etiquetas técnicas de evidencia", () => {
    render(
      <FloatingList
        opportunities={[opportunity]}
        explanations={{ [opportunity.listing_id]: explanation }}
        selectedId={null}
        hoverId={null}
        filter="all"
        onSelect={() => {}}
        onHover={() => {}}
      />,
    );

    expect(screen.getByText("El aviso sugiere buena luz natural.")).toBeVisible();
    expect(screen.queryByText(/evidencia (fuerte|media|baja|clara)/i)).not.toBeInTheDocument();
  });
});
