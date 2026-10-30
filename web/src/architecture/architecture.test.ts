import { describe, expect, it } from "vitest";
import { ARCHITECTURE as A } from "./data";
import { parseArchitecture } from "./load";
import { componentElements, elementsFor, fsmElements, pipelineElements, schemaElements, theoremsFor } from "./elements";
import { sourceUrl } from "./config";

const count = (els: { group?: string }[], g: string) => els.filter((e) => e.group === g).length;

describe("loader", () => {
  it("accepts the real file", () => expect(A.archVersion).toBe(1));
  it("rejects bad input", () => {
    expect(() => parseArchitecture({})).toThrow(/missing key/);
    expect(() => parseArchitecture({ ...A, archVersion: 99 })).toThrow(/archVersion/);
  });
});

describe("element builders", () => {
  it("schema", () => {
    const e = schemaElements(A);
    expect(count(e, "nodes")).toBe(A.schema.kinds.length);
    expect(count(e, "edges")).toBe(A.schema.arrows.length);
  });
  it("fsms", () => {
    for (const f of A.fsms) {
      const e = fsmElements(f);
      expect(count(e, "nodes")).toBe(f.states.length);
      expect(count(e, "edges")).toBe(new Set(f.transitions.map((t) => `${t.from}>${t.to}`)).size);
      expect(e.filter((x) => x.classes?.includes("start")).length).toBe(1);
      expect(e.filter((x) => x.classes?.includes("accept")).length).toBe(f.accept.length);
      expect(e.filter((x) => x.classes?.includes("sink")).length).toBe(f.implicit.state ? 1 : 0);
    }
  });
  it("pipeline", () => {
    const e = pipelineElements(A);
    expect(count(e, "nodes")).toBe(A.pipeline.stages.length);
    expect(count(e, "edges")).toBe(A.pipeline.edges.length);
  });
  it("components", () => {
    const e = componentElements(A);
    expect(count(e, "nodes")).toBe(A.components.components.length);
    expect(count(e, "edges")).toBe(A.components.edges.length);
  });
  it("elementsFor covers every diagram", () => {
    for (const d of ["schema", "gaitFsm", "uiFsm", "pipeline", "components"] as const) expect(elementsFor(A, d).length).toBeGreaterThan(0);
  });
});

describe("links", () => {
  it("filters theorems by module", () => {
    const m = A.theorems[0]!.loc.module;
    expect(theoremsFor(A, m).every((t) => t.loc.module === m)).toBe(true);
    expect(theoremsFor(A, null).length).toBe(A.theorems.length);
  });
  it("source url", () => {
    expect(sourceUrl({ file: "a.lean", line: 3 }, "")).toBeNull();
    expect(sourceUrl({ file: "a.lean", line: 3 }, "https://x/blob/main/")).toBe("https://x/blob/main/a.lean#L3");
  });
});
