import { readFileSync, existsSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseMeshIndex } from "./meshIndex";

const dir = new URL("../../../data/out/meshes/", import.meta.url);
const raw = JSON.parse(readFileSync(new URL("index.json", dir), "utf8"));
const paths = JSON.parse(readFileSync(new URL("../muscle_paths.json", dir), "utf8"));

describe("bm-meshes/1", () => {
  const index = parseMeshIndex(raw);

  it("lists the 13 bodies, each with an existing glTF file", () => {
    expect(index.bodies).toHaveLength(13);
    for (const b of index.bodies) {
      expect(existsSync(new URL(b.file, dir))).toBe(true);
      expect(b.triangles).toBeGreaterThan(0);
    }
  });

  it("points at the per-frame poses, which exist for every body", () => {
    expect(index.transforms).toEqual({ file: "../muscle_paths.json", key: "bodies" });
    for (const b of index.bodies) expect(paths[index.transforms.key][b.body]).toHaveLength(paths.time.length);
  });

  it("embeds a valid glTF 2.0 document per body", () => {
    for (const b of index.bodies) {
      const g = JSON.parse(readFileSync(new URL(b.file, dir), "utf8"));
      expect(g.asset.version).toBe("2.0");
      expect(g.buffers[0].uri).toMatch(/^data:/);
    }
  });

  it("rejects other formats", () => {
    expect(() => parseMeshIndex({ ...raw, format: "bm-meshes/9" })).toThrow(/format/);
  });
});
