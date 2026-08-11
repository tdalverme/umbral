/** Client-side notifications access through the BFF routes (H5). */

export type NotificationPrefState = "active" | "paused" | "disabled";

export interface NotificationPreferences {
  email_enabled: boolean;
  inbox_enabled: boolean;
  timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  digest_enabled: boolean;
  digest_local_hour: number;
  score_threshold: number;
  state: NotificationPrefState;
  version: number;
}

export interface InboxItem {
  decision_id: string;
  reason_code: string;
  trigger: string;
  read: boolean;
  created_at: string;
}

export interface InboxPage {
  items: InboxItem[];
}

export interface PreferencesInput {
  email_enabled: boolean;
  inbox_enabled: boolean;
  timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  digest_enabled: boolean;
  digest_local_hour: number;
  score_threshold: number;
  state: NotificationPrefState;
}

interface Problem {
  code?: string;
  detail?: string;
}

async function parseResponse(response: Response): Promise<unknown> {
  if (response.ok) {
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  }
  let problem: Problem | null = null;
  try {
    problem = (await response.json()) as Problem;
  } catch {
    problem = null;
  }
  throw new Error(problem?.code ?? `http.${response.status}`);
}

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(path, {
    headers: { "X-Correlation-ID": crypto.randomUUID() },
    cache: "no-store",
  });
  return parseResponse(response);
}

async function sendJson(path: string, method: string, body: unknown): Promise<unknown> {
  const response = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Correlation-ID": crypto.randomUUID(),
    },
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}

export const notificationsApi = {
  getPreferences: async (): Promise<NotificationPreferences> =>
    (await getJson("/api/notifications/preferences")) as NotificationPreferences,
  updatePreferences: async (body: PreferencesInput): Promise<NotificationPreferences> =>
    (await sendJson("/api/notifications/preferences", "PUT", body)) as NotificationPreferences,
  listInbox: async (pageSize = 50): Promise<InboxPage> =>
    (await getJson(`/api/notifications/inbox?page_size=${pageSize}`)) as InboxPage,
  markRead: async (decisionId: string, read: boolean): Promise<InboxItem> =>
    (await sendJson(`/api/notifications/inbox/${decisionId}`, "PATCH", { read })) as InboxItem,
  unsubscribe: async (token: string): Promise<void> => {
    const response = await fetch("/api/notifications/unsubscribe", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Correlation-ID": crypto.randomUUID(),
      },
      body: JSON.stringify({ token }),
    });
    if (!response.ok && response.status !== 204) {
      await parseResponse(response);
    }
  },
};
