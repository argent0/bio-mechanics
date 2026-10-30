import BioMech.Acyclic

/-!
# Front-end components

## Terms

* *Region*: the body region of an anatomy node, `Region` in
  `BioMech.Schema` (lower limb, pelvis, trunk, upper limb, head).
* *Side*: left, right, or midline, the node's `side` attribute (`Side` in
  `BioMech.Schema`).

The web app's modules form a digraph of allowed imports: an edge `a → b` means
code in `a` may import code in `b`. Workstream C emits
`generated/eslint-boundaries.json` from `edges` and `Component.paths`, so an
import outside this graph fails the lint.

Every component may also import the generated types and FSM tables under
`sharedImports`; those sit outside the graph.

Layers, from the bottom: `GraphStore` holds `graph.json`; `QueryEngine` answers
questions over it; the UI components (`ui`) read through `QueryEngine`;
`RegionFilter` holds the selected body regions and sides and narrows the nodes
a view passes it, so the views that show muscles take their nodes from
`QueryEngine` and filter them through `RegionFilter`; `Viewer3D` and
`PhasePanel` follow `Timeline` for the current time and phase, and
`PhasePanel` borrows `Viewer3D`'s muscle colour scale; `ArchitectureView`
reads generated files only; `TraceRecorder` records FSM events from every UI
component; `App` wires everything together.

Theorems: the import graph is acyclic; the UI components that use the
knowledge graph reach `GraphStore` only through `QueryEngine`;
`RegionFilter` and `ArchitectureView` each reach exactly one component,
`TraceRecorder`.
-/

namespace BioMech.Components

open BioMech

/-- Front-end modules, each owning paths under `web/src/`: one directory per
component, two files for `App`. -/
inductive Component
  /-- Loads `graph.json` and holds its nodes and edges. -/
  | GraphStore
  /-- Answers graph queries: neighbours, roles per phase, movement drill-down. -/
  | QueryEngine
  /-- Scrubbable gait cycle with phase bands; owns the current time and phase. -/
  | Timeline
  /-- Three.js skeleton with muscles as tubes, coloured by activation. -/
  | Viewer3D
  /-- Joint actions and muscle roles for the current phase, in plain language. -/
  | PhasePanel
  /-- The selected body regions and sides, with the checkbox control that
  picks them; narrows the nodes a view passes it to those regions and sides,
  reading each node's `region` and `side` attributes. -/
  | RegionFilter
  /-- Cytoscape.js view of a node and its neighbours. -/
  | GraphView
  /-- The `/architecture` page, drawn from `generated/architecture.json`. -/
  | ArchitectureView
  /-- Dev-mode recorder of FSM event traces to `trace.json`. -/
  | TraceRecorder
  /-- Entry point: loads the graph source (`config.ts`), builds the store and
  engine, and mounts the UI components. -/
  | App
  deriving DecidableEq, Repr, Inhabited

/-- Every component, in declaration order. -/
def Component.all : List Component :=
  [.GraphStore, .QueryEngine, .Timeline, .Viewer3D, .PhasePanel, .RegionFilter,
   .GraphView, .ArchitectureView, .TraceRecorder, .App]

/-- `Component.all` lists every component. -/
theorem Component.mem_all (c : Component) : c ∈ Component.all := by cases c <;> decide

/-- `Component.all` lists each component once. -/
theorem Component.nodup_all : Component.all.Nodup := by decide

instance : Fintype Component :=
  ⟨⟨Component.all, Multiset.coe_nodup.mpr Component.nodup_all⟩, Component.mem_all⟩

/-- Component name as written in Lean, e.g. `GraphStore`. -/
def Component.name : Component → String
  | .GraphStore => "GraphStore"
  | .QueryEngine => "QueryEngine"
  | .Timeline => "Timeline"
  | .Viewer3D => "Viewer3D"
  | .PhasePanel => "PhasePanel"
  | .RegionFilter => "RegionFilter"
  | .GraphView => "GraphView"
  | .ArchitectureView => "ArchitectureView"
  | .TraceRecorder => "TraceRecorder"
  | .App => "App"

/-- Where the component's code lives, relative to the repository root. A
trailing `/` marks a directory; any other path names one file. Each component
owns one directory, and `App` owns the two files of the entry point. -/
def Component.paths : Component → List String
  | .GraphStore => ["web/src/store/"]
  | .QueryEngine => ["web/src/query/"]
  | .Timeline => ["web/src/timeline/"]
  | .Viewer3D => ["web/src/viewer/"]
  | .PhasePanel => ["web/src/phase/"]
  | .RegionFilter => ["web/src/region/"]
  | .GraphView => ["web/src/graphview/"]
  | .ArchitectureView => ["web/src/architecture/"]
  | .TraceRecorder => ["web/src/trace/"]
  | .App => ["web/src/main.ts", "web/src/config.ts"]

/-- Each path belongs to exactly one component. -/
theorem Component.nodup_paths : (Component.all.flatMap Component.paths).Nodup := by decide

/-- Paths every component may import, outside the component graph: the
generated types and FSM tables. -/
def sharedImports : List String := ["generated/ts/"]

/-- The UI components: everything the app mounts on screen. -/
def ui : List Component :=
  [.Timeline, .Viewer3D, .PhasePanel, .RegionFilter, .GraphView, .ArchitectureView]

/-- Allowed imports: `a → b` means `a` may import `b`. -/
def edges : List (Component × Component) :=
  [ -- the query layer reads the store
    (.QueryEngine, .GraphStore),
    -- views that use the knowledge graph read through the query layer
    (.Timeline, .QueryEngine), (.Viewer3D, .QueryEngine),
    (.PhasePanel, .QueryEngine), (.GraphView, .QueryEngine),
    -- views that show muscles narrow them to the selected regions and sides
    (.Viewer3D, .RegionFilter), (.PhasePanel, .RegionFilter),
    (.GraphView, .RegionFilter),
    -- views that follow the current time and phase
    (.Viewer3D, .Timeline), (.PhasePanel, .Timeline),
    -- the dynamics panel colours muscles with the viewer's colour scale
    (.PhasePanel, .Viewer3D),
    -- every UI component records its FSM events
    (.Timeline, .TraceRecorder), (.Viewer3D, .TraceRecorder),
    (.PhasePanel, .TraceRecorder), (.RegionFilter, .TraceRecorder),
    (.GraphView, .TraceRecorder), (.ArchitectureView, .TraceRecorder),
    -- the entry point wires everything
    (.App, .GraphStore), (.App, .QueryEngine), (.App, .TraceRecorder),
    (.App, .Timeline), (.App, .Viewer3D), (.App, .PhasePanel),
    (.App, .RegionFilter), (.App, .GraphView), (.App, .ArchitectureView)]

/-- The import digraph: adjacency is membership in `edges`. -/
abbrev graph : Digraph Component := ofEdges edges

/-! ## Order -/

/-- Components ordered so that each one comes after every component that
imports it: Kahn's algorithm over `edges`. Diagrams draw importers above the
modules they import. -/
def topoOrder : List Component := topoSort Component.all edges

/-- `topoOrder` lists every component once, each importer before the modules
it imports. -/
theorem isTopoOrder_topoOrder : IsTopoOrder graph topoOrder := by decide

/-- The import graph is acyclic, decided through reachability. -/
theorem acyclic : Acyclic graph := by decide

/-! ## Layering -/

/-- `Viewer3D` reaches `GraphStore`, and only through `QueryEngine`. -/
theorem viewer3D_via_queryEngine : ReachesOnlyVia graph .Viewer3D .QueryEngine .GraphStore := by
  decide

/-- `PhasePanel` reaches `GraphStore`, and only through `QueryEngine`. -/
theorem phasePanel_via_queryEngine :
    ReachesOnlyVia graph .PhasePanel .QueryEngine .GraphStore := by
  decide

/-- `GraphView` reaches `GraphStore`, and only through `QueryEngine`. -/
theorem graphView_via_queryEngine : ReachesOnlyVia graph .GraphView .QueryEngine .GraphStore := by
  decide

/-- `Timeline` reaches `GraphStore`, and only through `QueryEngine`. -/
theorem timeline_via_queryEngine : ReachesOnlyVia graph .Timeline .QueryEngine .GraphStore := by
  decide

/-- The general rule behind the four theorems above: once `QueryEngine` is
deleted, `App` is the one component that still reaches `GraphStore`. -/
theorem graphStore_behind_queryEngine : ∀ c, c ≠ .App → c ≠ .QueryEngine →
    ¬ Relation.TransGen (deleteVertex graph .QueryEngine).Adj c .GraphStore := by
  decide

/-- `QueryEngine` and `App` are the two direct importers of `GraphStore`. -/
theorem graphStore_importers : ∀ c, graph.Adj c .GraphStore ↔ c = .QueryEngine ∨ c = .App := by
  decide

/-- `ArchitectureView` reaches exactly `TraceRecorder`: it stays clear of the
store and the query layer. -/
theorem architectureView_reach :
    ∀ c, Relation.TransGen graph.Adj .ArchitectureView c ↔ c = .TraceRecorder := by
  decide

/-- The views that show muscles (`Viewer3D`, `PhasePanel`, `GraphView`) and
`App` are the direct importers of `RegionFilter`. -/
theorem regionFilter_importers : ∀ c, graph.Adj c .RegionFilter ↔
    c = .Viewer3D ∨ c = .PhasePanel ∨ c = .GraphView ∨ c = .App := by
  decide

/-- `RegionFilter` reaches exactly `TraceRecorder`: it works on the nodes its
importers pass it and stays clear of the store and the query layer. -/
theorem regionFilter_reach :
    ∀ c, Relation.TransGen graph.Adj .RegionFilter c ↔ c = .TraceRecorder := by
  decide

/-- Every UI component may import `TraceRecorder`. -/
theorem ui_imports_traceRecorder : ∀ c ∈ ui, graph.Adj c .TraceRecorder := by decide

/-- `GraphStore` and `TraceRecorder` are leaves: their imports stay within
`sharedImports`. -/
theorem leaves : ∀ c, ¬ graph.Adj .GraphStore c ∧ ¬ graph.Adj .TraceRecorder c := by decide

/-- `App` is the root: it reaches every other component, and every other
component stays clear of it. -/
theorem app_root : ∀ c, c ≠ .App →
    Relation.TransGen graph.Adj .App c ∧ ¬ Relation.TransGen graph.Adj c .App := by
  decide

end BioMech.Components
