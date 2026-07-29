import { createClient, type Client } from "./generated/client";

function apiBaseUrl(): string {
  const baseUrl = process.env.UMBRAL_API_BASE_URL;
  if (!baseUrl) {
    throw new Error("UMBRAL_API_BASE_URL is required for server API requests");
  }
  return baseUrl;
}

export function createServerApiClient(): Client {
  return createClient({ baseUrl: apiBaseUrl() });
}
