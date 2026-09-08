import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OpportunityDetailSheet } from "./opportunity-detail-sheet";
import type { Explanation } from "@/lib/radar/client";

const opportunity = {
  listing_id: "listing-1",
  neighborhood: "palermo",
  total_cost: 207000,
  surface_m2: 54,
  rooms: 2,
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

describe("OpportunityDetailSheet", () => {
  it("muestra la narrativa fundada antes de las razones deterministas", () => {
    render(
      <OpportunityDetailSheet
        opportunity={opportunity}
        explanation={explanation}
        narrative={{
          text: "Encaja especialmente por la luz y la zona residencial.",
          used_criteria: ["luminosidad"],
          used_evidence_refs: ["observation:light-1"],
          source: "managed",
          prompt_version: "explanation-narrative-v1",
          model_version: "test-model",
        }}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Encaja especialmente por la luz y la zona residencial.")).toBeVisible();
    expect(screen.queryByText(/evidencia (fuerte|media|baja|clara)/i)).not.toBeInTheDocument();
  });

  it("traduce un reparo activo sin filtrar su texto interno", () => {
    render(
      <OpportunityDetailSheet
        opportunity={opportunity}
        explanation={{
          ...explanation,
          risks: [{
            criterion_key: "vida_nocturna",
            state: "mismatch",
            reason_code: "concept_missing",
            text: "nightlife_intensity no coincide.",
          }],
        }}
        narrative={{
          text: "Encaja por la luz natural.",
          used_criteria: ["luminosidad", "vida_nocturna"],
          used_evidence_refs: [],
          source: "managed",
          prompt_version: "explanation-narrative-v1",
          model_version: "test-model",
        }}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /antes de decidir/i }));

    expect(screen.getByText(/La actividad nocturna es un punto para revisar antes de decidir\./)).toBeVisible();
    expect(screen.queryByText(/nightlife_intensity/i)).not.toBeInTheDocument();
  });

  it("mantiene neutral la causa de un dato desconocido", () => {
    render(
      <OpportunityDetailSheet
        opportunity={opportunity}
        explanation={{ ...explanation, risks: [], missing_data: ["vida_nocturna"] }}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /antes de decidir/i }));

    expect(screen.getByText(/No puedo confirmar actividad nocturna todavía\./)).toBeVisible();
    expect(screen.queryByText(/el aviso no lo informa/i)).not.toBeInTheDocument();
  });
});
