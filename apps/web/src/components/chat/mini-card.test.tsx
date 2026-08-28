import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MiniCard } from "@/components/chat/mini-card";

describe("MiniCard", () => {
  it("enlaza al detalle del listing con el contexto del radar", () => {
    render(<MiniCard listingId="abc-123" profileId="prof-1" runId="run-1" />);
    const link = screen.getByRole("link", { name: /ver ficha/i });
    expect(link).toHaveAttribute("href", "/listings/abc-123?profile=prof-1&run=run-1");
  });
});
