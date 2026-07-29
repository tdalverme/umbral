import { createClient, type Client } from "./generated/client";

export function createBrowserApiClient(): Client {
  return createClient({ baseUrl: window.location.origin });
}
