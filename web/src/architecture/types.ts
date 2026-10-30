/** Types mirroring `generated/architecture.json`. Source of truth: the docstring of spec/BioMech/Gen/ArchJson.lean. */
export interface Loc { module: string; file: string; line: number; startLine: number; endLine: number }
export interface Item { name: string; doc: string | null }
export interface SchemaArrow { name: string; source: string; target: string; attrs: string | null }
export interface Schema {
  graphSchemaVersion: number; loc: Loc; kinds: Item[]; arrows: SchemaArrow[];
  structs: { name: string; doc: string | null; fields: { name: string; type: string; doc: string | null }[] }[];
  enums: { name: string; doc: string | null; values: string[] }[];
}
export type FsmId = "gaitFsm" | "uiFsm";
export interface Fsm {
  id: FsmId; module: string; loc: Loc; stateType: string; eventType: string;
  stateDoc: string | null; eventDoc: string | null;
  states: Item[]; events: Item[]; start: string; accept: string[];
  transitions: { from: string; event: string; to: string }[];
  implicit: { kind: "sink" | "selfLoop" | "mixed"; state: string | null };
  table: { from: string; to: string[] }[];
  stateLists: { name: string; doc: string | null; values: string[] }[];
  words: { name: string; doc: string | null; events: string[] }[];
}
export interface Stage {
  name: string; doc: string | null; script: string; module: string;
  reads: string[]; writes: string[]; inputs: string[]; outputs: string[];
}
export interface Pipeline {
  loc: Loc; stages: Stage[]; edges: { source: string; target: string; artefacts: string[] }[];
  topoOrder: string[];
  artefacts: { name: string; doc: string | null; path: string; isSource: boolean; isDirectory: boolean }[];
}
export interface Components {
  loc: Loc; components: { name: string; doc: string | null; paths: string[] }[];
  edges: { source: string; target: string }[]; topoOrder: string[]; sharedImports: string[];
}
export interface TheoremEntry { name: string; namespace: string; statement: string; doc: string | null; loc: Loc }
export interface Architecture {
  $generated: string; archVersion: number; schema: Schema; fsms: Fsm[];
  pipeline: Pipeline; components: Components; theorems: TheoremEntry[];
}
export type DiagramId = "schema" | "gaitFsm" | "uiFsm" | "pipeline" | "components";
