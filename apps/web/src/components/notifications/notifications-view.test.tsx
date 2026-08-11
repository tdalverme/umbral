import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NotificationsView } from "./notifications-view";

vi.mock("@/lib/notifications/client", () => ({
  notificationsApi: {
    listInbox: vi.fn().mockResolvedValue({ items: [] }),
    updatePreferences: vi.fn(),
    markRead: vi.fn(),
    unsubscribe: vi.fn(),
  },
}));

const preferences = {
  email_enabled: true,
  inbox_enabled: true,
  timezone: "America/Argentina/Buenos_Aires",
  quiet_hours_start: "22:00",
  quiet_hours_end: "08:00",
  digest_enabled: true,
  digest_local_hour: 9,
  score_threshold: 0.6,
  state: "active" as const,
  version: 1,
};

describe("NotificationsView", () => {
  it("renders the preference summary read-only by default", () => {
    render(<NotificationsView initialPreferences={preferences} />);
    expect(screen.getByText("Preferencias de alerta")).toBeDefined();
    expect(screen.getByText(/Umbral de score 0.60/)).toBeDefined();
    expect(screen.getByText("Desactivar alertas")).toBeDefined();
  });

  it("renders the notification center with empty state", () => {
    render(<NotificationsView initialPreferences={preferences} />);
    expect(screen.getByText("Centro de notificaciones")).toBeDefined();
  });

  it("does not render with missing preferences as a crash", () => {
    render(<NotificationsView initialPreferences={null} />);
    expect(screen.getByText("Sin preferencias configuradas.")).toBeDefined();
  });
});
