import { forwardRadarRequest } from "@/lib/radar/server";

import { NotificationsView } from "@/components/notifications/notifications-view";
import type { NotificationPreferences } from "@/lib/notifications/client";

export const metadata = { title: "Notificaciones" };

export default async function NotificationsPage(): Promise<React.ReactNode> {
  const response = await forwardRadarRequest("/api/v1/notifications/preferences", {});
  let preferences: NotificationPreferences | null = null;
  if (response.ok) {
    try {
      preferences = (await response.json()) as NotificationPreferences;
    } catch {
      preferences = null;
    }
  }
  return <NotificationsView initialPreferences={preferences} />;
}
