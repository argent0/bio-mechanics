/**
 * Parsing of `meshes/index.json` (format `bm-meshes/1`, written by `pipeline/export_meshes.py`,
 * whose module docstring defines the fields). One glTF file per body, in the body frame
 * (metres, y up); the per-frame body poses live in `muscle_paths.json` under `bodies`.
 */

export const MESH_FORMAT = "bm-meshes/1";

export interface MeshBody {
  body: string;
  /** glTF file name beside `index.json`. */
  file: string;
  vertices: number;
  triangles: number;
}

export interface MeshIndex {
  bodies: MeshBody[];
  /** Where the body poses live: file name and key in it. */
  transforms: { file: string; key: string };
}

const isObject = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);

export function parseMeshIndex(json: unknown): MeshIndex {
  if (!isObject(json) || json["format"] !== MESH_FORMAT) throw new Error(`meshes/index.json: format ${MESH_FORMAT} expected`);
  if (json["units"] !== "m") throw new Error("meshes/index.json: units must be m");
  const list = json["bodies"];
  if (!Array.isArray(list) || list.length === 0) throw new Error("meshes/index.json: bodies missing");
  const bodies = list.map((b, i): MeshBody => {
    if (!isObject(b) || typeof b["body"] !== "string" || typeof b["file"] !== "string") throw new Error(`meshes/index.json: bodies[${i}] needs body and file`);
    return { body: b["body"], file: b["file"], vertices: Number(b["vertices"] ?? 0), triangles: Number(b["triangles"] ?? 0) };
  });
  const t = json["transforms"];
  if (!isObject(t) || typeof t["file"] !== "string" || typeof t["key"] !== "string") throw new Error("meshes/index.json: transforms needs file and key");
  return { bodies, transforms: { file: t["file"], key: t["key"] } };
}
