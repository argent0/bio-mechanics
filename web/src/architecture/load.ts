import type { Architecture } from "./types";

export const SUPPORTED_ARCH_VERSION = 1;
const TOP_KEYS = ["archVersion", "schema", "fsms", "pipeline", "components", "theorems"] as const;

/** Check the top-level keys and `archVersion`; the nested shape is trusted from the generator. */
export function parseArchitecture(raw: unknown): Architecture {
  if (typeof raw !== "object" || raw === null) throw new Error("architecture.json: not an object");
  const o = raw as Record<string, unknown>;
  for (const k of TOP_KEYS) if (!(k in o)) throw new Error(`architecture.json: missing key "${k}"`);
  if (o.archVersion !== SUPPORTED_ARCH_VERSION)
    throw new Error(`architecture.json: archVersion ${String(o.archVersion)}, expected ${SUPPORTED_ARCH_VERSION}`);
  return raw as Architecture;
}
