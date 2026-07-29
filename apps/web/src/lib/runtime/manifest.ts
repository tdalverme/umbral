import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

const RELEASE_ID_PATTERN = /^[A-Za-z0-9._-]{1,100}$/;
const GIT_SHA_PATTERN = /^[0-9a-f]{40}$/;
const DIGEST_PATTERN = /^sha256:[0-9a-f]{64}$/;

export type RuntimeArtifact = Readonly<{
  image: string;
  digest: string;
  platform: "linux/amd64";
  provenance?: string;
}>;

export type RuntimeManifest = Readonly<{
  release_id: string;
  git_sha: string;
  built_at: string;
  contract_major: 1;
  database_revision: string;
  config_schema_version: number;
  artifacts: Readonly<{
    web: RuntimeArtifact;
    runtime: RuntimeArtifact;
  }>;
  manifest_sha256: string;
}>;

export class RuntimeManifestError extends Error {
  constructor() {
    super("runtime release manifest is unavailable");
    this.name = "RuntimeManifestError";
  }
}

function configuredManifestPath(): string {
  const configured = process.env.UMBRAL_RELEASE_MANIFEST?.trim();
  if (!configured) throw new RuntimeManifestError();
  return path.resolve(process.cwd(), configured);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function validateArtifact(value: unknown): RuntimeArtifact | null {
  if (!isRecord(value)) return null;
  const keys = Object.keys(value);
  const hasProvenance = keys.includes("provenance");
  const expectedKeys = hasProvenance ? ["digest", "image", "platform", "provenance"] : ["digest", "image", "platform"];
  if (keys.some((key) => !expectedKeys.includes(key)) || keys.length !== expectedKeys.length) return null;
  if (!stringField(value.image) || value.image.length > 300) return null;
  if (typeof value.digest !== "string" || !DIGEST_PATTERN.test(value.digest)) return null;
  if (value.platform !== "linux/amd64") return null;
  if (hasProvenance && (!stringField(value.provenance) || !URL.canParse(value.provenance))) return null;
  return {
    image: value.image,
    digest: value.digest,
    platform: "linux/amd64",
    ...(hasProvenance ? { provenance: value.provenance as string } : {}),
  };
}

function validateManifest(value: unknown, manifestSha256: string): RuntimeManifest {
  if (!isRecord(value)) throw new RuntimeManifestError();
  const expectedKeys = [
    "artifacts",
    "built_at",
    "config_schema_version",
    "contract_major",
    "database_revision",
    "git_sha",
    "release_id",
    "schema_version",
  ];
  const keys = Object.keys(value);
  if (keys.length !== expectedKeys.length || keys.some((key) => !expectedKeys.includes(key))) throw new RuntimeManifestError();
  if (value.schema_version !== 1 || value.contract_major !== 1) throw new RuntimeManifestError();
  if (typeof value.config_schema_version !== "number" || !Number.isInteger(value.config_schema_version) || value.config_schema_version < 1) {
    throw new RuntimeManifestError();
  }
  if (typeof value.release_id !== "string" || !RELEASE_ID_PATTERN.test(value.release_id)) throw new RuntimeManifestError();
  if (typeof value.git_sha !== "string" || !GIT_SHA_PATTERN.test(value.git_sha)) throw new RuntimeManifestError();
  if (typeof value.built_at !== "string" || !value.built_at.endsWith("Z") || Number.isNaN(Date.parse(value.built_at))) {
    throw new RuntimeManifestError();
  }
  if (typeof value.database_revision !== "string" || value.database_revision.length < 1 || value.database_revision.length > 64) {
    throw new RuntimeManifestError();
  }
  if (!isRecord(value.artifacts) || Object.keys(value.artifacts).length !== 2 || !Object.keys(value.artifacts).every((key) => key === "web" || key === "runtime")) {
    throw new RuntimeManifestError();
  }
  const web = validateArtifact(value.artifacts.web);
  const runtime = validateArtifact(value.artifacts.runtime);
  if (!web || !runtime) throw new RuntimeManifestError();
  return {
    release_id: value.release_id,
    git_sha: value.git_sha,
    built_at: value.built_at,
    contract_major: 1,
    database_revision: value.database_revision,
    config_schema_version: value.config_schema_version,
    artifacts: { web, runtime },
    manifest_sha256: manifestSha256,
  };
}

export async function loadRuntimeManifest(): Promise<RuntimeManifest> {
  let rawBytes: Buffer;
  try {
    rawBytes = await readFile(configuredManifestPath());
  } catch {
    throw new RuntimeManifestError();
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawBytes.toString("utf8")) as unknown;
  } catch {
    throw new RuntimeManifestError();
  }
  return validateManifest(parsed, createHash("sha256").update(rawBytes).digest("hex"));
}

export function versionFromManifest(manifest: RuntimeManifest): Record<string, unknown> {
  return {
    surface: "web",
    release_id: manifest.release_id,
    git_sha: manifest.git_sha,
    artifact_digest: manifest.artifacts.web.digest,
    manifest_sha256: manifest.manifest_sha256,
    contract_major: manifest.contract_major,
    database_revision: manifest.database_revision,
    built_at: manifest.built_at,
  };
}
