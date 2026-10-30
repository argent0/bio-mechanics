import BioMech.Acyclic

/-!
# Build pipeline

The offline data pipeline is a digraph of stages: an edge `a → b` means stage
`b` runs after stage `a`. Each stage is one Python script under `pipeline/`
that reads and writes the files listed here. Workstream C emits
`generated/pipeline.ninja` from this file: one build edge per stage, in
`topoOrder`, with `Stage.inputs` as dependencies and `Stage.outputs` as
targets.

Files fall into three groups, by directory (`Dir`):
* sources, maintained outside the pipeline: `data/raw/` (downloads),
  `data/curated/` (hand-written anatomy), `pipeline/config/` (thresholds);
* intermediate results in `data/work/`;
* outputs the web app loads, in `data/out/`.

Theorems: the stage graph is acyclic and `topoOrder` is a topological order of
it; every input of a stage is a source or an output of a stage upstream of it;
each derived file has exactly one writer.
-/

namespace BioMech.Pipeline

/-- Pipeline stages, in handover order. -/
inductive Stage
  /-- Load the Rajagopal model and the walking trial with the OpenSim API. -/
  | loadModel
  /-- Static optimisation: muscle activations per frame. -/
  | runStaticOpt
  /-- Moment arm and muscle-tendon length per muscle, coordinate, and frame;
  length velocity gives concentric or eccentric work. -/
  | computeMomentArms
  /-- Detect gait events and drive the generated gait FSM to label each frame
  with its phase. -/
  | segmentPhases
  /-- Classify each muscle per phase and joint action as main mover, helper,
  stabiliser, or antagonist. -/
  | labelRoles
  /-- Add common names, ontology identifiers, attachments, and innervation. -/
  | enrichAnatomy
  /-- Write the knowledge graph `data/out/graph.json` (contract C3). -/
  | exportGraph
  /-- Convert the model's bone geometry to glTF. -/
  | exportMeshes
  /-- Write muscle path points per frame for the tube renderer. -/
  | exportMusclePaths
  deriving DecidableEq, Repr, Inhabited

/-- Every stage, in declaration order. -/
def Stage.all : List Stage :=
  [.loadModel, .runStaticOpt, .computeMomentArms, .segmentPhases, .labelRoles,
   .enrichAnatomy, .exportGraph, .exportMeshes, .exportMusclePaths]

/-- `Stage.all` lists every stage. -/
theorem Stage.mem_all (s : Stage) : s ∈ Stage.all := by cases s <;> decide

/-- `Stage.all` lists each stage once. -/
theorem Stage.nodup_all : Stage.all.Nodup := by decide

instance : Fintype Stage := ⟨⟨Stage.all, Multiset.coe_nodup.mpr Stage.nodup_all⟩, Stage.mem_all⟩

/-- Stage name as written in Lean, e.g. `loadModel`. -/
def Stage.name : Stage → String
  | .loadModel => "loadModel"
  | .runStaticOpt => "runStaticOpt"
  | .computeMomentArms => "computeMomentArms"
  | .segmentPhases => "segmentPhases"
  | .labelRoles => "labelRoles"
  | .enrichAnatomy => "enrichAnatomy"
  | .exportGraph => "exportGraph"
  | .exportMeshes => "exportMeshes"
  | .exportMusclePaths => "exportMusclePaths"

/-- The Python script that runs the stage, relative to the repository root. -/
def Stage.script : Stage → String
  | .loadModel => "pipeline/load_model.py"
  | .runStaticOpt => "pipeline/static_opt.py"
  | .computeMomentArms => "pipeline/moment_arms.py"
  | .segmentPhases => "pipeline/segment_phases.py"
  | .labelRoles => "pipeline/label_roles.py"
  | .enrichAnatomy => "pipeline/enrich_anatomy.py"
  | .exportGraph => "pipeline/export_graph.py"
  | .exportMeshes => "pipeline/export_meshes.py"
  | .exportMusclePaths => "pipeline/export_muscle_paths.py"

/-- Stage order: `a → b` means `b` runs after `a`. -/
def edges : List (Stage × Stage) :=
  [(.loadModel, .runStaticOpt), (.runStaticOpt, .computeMomentArms),
   (.computeMomentArms, .segmentPhases), (.segmentPhases, .labelRoles),
   (.labelRoles, .enrichAnatomy), (.enrichAnatomy, .exportGraph),
   (.loadModel, .exportMeshes),
   (.computeMomentArms, .exportMusclePaths), (.runStaticOpt, .exportMusclePaths)]

/-- The stage digraph: adjacency is membership in `edges`. -/
abbrev graph : Digraph Stage := ofEdges edges

/-! ## Files -/

/-- The directory a pipeline file lives in. -/
inductive Dir
  /-- Downloads: the OpenSim model, the walking trial, ontology subsets. -/
  | raw
  /-- Hand-written anatomy facts. -/
  | curated
  /-- Pipeline settings, recorded in the output. -/
  | config
  /-- Intermediate results, passed between stages. -/
  | work
  /-- Results the web app loads. -/
  | out
  deriving DecidableEq, Repr, Inhabited

/-- The directory's path, relative to the repository root, with a trailing `/`. -/
def Dir.root : Dir → String
  | .raw => "data/raw/"
  | .curated => "data/curated/"
  | .config => "pipeline/config/"
  | .work => "data/work/"
  | .out => "data/out/"

/-- Sources come from outside the pipeline; the pipeline derives the rest. -/
def Dir.isSource : Dir → Bool
  | .raw | .curated | .config => true
  | .work | .out => false

/-- Every file the pipeline reads or writes. -/
inductive Artefact
  /-- The Rajagopal full-body OpenSim model. -/
  | osimModel
  /-- The bone surface meshes (`.vtp`) the model refers to. -/
  | geometry
  /-- Joint coordinates per frame of the walking trial (inverse kinematics). -/
  | ikMotion
  /-- Ground reaction forces and centres of pressure per frame of the trial. -/
  | grfMotion
  /-- OpenSim external-loads setup: which body each ground reaction force acts on. -/
  | externalLoads
  /-- Uberon subset: anatomy terms and part-of relations. -/
  | uberon
  /-- FMA subset: attachments and innervation. -/
  | fma
  /-- Hand-curated common names, attachments, and innervation. -/
  | curatedAnatomy
  /-- Role-classification thresholds. -/
  | roleThresholds
  /-- Bodies, joints, coordinates, and muscles of the model, with OpenSim names. -/
  | model
  /-- Joint coordinate values and speeds per frame. -/
  | kinematics
  /-- Ground reaction forces per frame, on the kinematics time base. -/
  | grf
  /-- Activation in 0–1 per muscle and frame. -/
  | activations
  /-- Moment arm in metres per muscle, coordinate, and frame. -/
  | momentArms
  /-- Muscle-tendon length and lengthening velocity per muscle and frame. -/
  | mtLengths
  /-- Gait phase per frame, with gait event times. -/
  | phases
  /-- Per phase and joint action: each muscle's role, contraction, activation,
  and moment arm. -/
  | roles
  /-- `roles` plus anatomy: common names, ontology identifiers, attachments,
  innervation. -/
  | enriched
  /-- The knowledge graph (contract C3). -/
  | knowledgeGraph
  /-- Manifest of the bone meshes; one glTF file per body sits beside it. -/
  | meshes
  /-- Muscle path points, activation, and lengthening velocity per frame. -/
  | musclePaths
  deriving DecidableEq, Repr, Inhabited

/-- Every artefact, in declaration order. -/
def Artefact.all : List Artefact :=
  [.osimModel, .geometry, .ikMotion, .grfMotion, .externalLoads, .uberon, .fma,
   .curatedAnatomy, .roleThresholds,
   .model, .kinematics, .grf, .activations, .momentArms, .mtLengths, .phases,
   .roles, .enriched,
   .knowledgeGraph, .meshes, .musclePaths]

/-- `Artefact.all` lists every artefact. -/
theorem Artefact.mem_all (a : Artefact) : a ∈ Artefact.all := by cases a <;> decide

/-- `Artefact.all` lists each artefact once. -/
theorem Artefact.nodup_all : Artefact.all.Nodup := by decide

instance : Fintype Artefact :=
  ⟨⟨Artefact.all, Multiset.coe_nodup.mpr Artefact.nodup_all⟩, Artefact.mem_all⟩

/-- The directory an artefact lives in. -/
def Artefact.dir : Artefact → Dir
  | .osimModel | .geometry | .ikMotion | .grfMotion | .externalLoads
  | .uberon | .fma => .raw
  | .curatedAnatomy => .curated
  | .roleThresholds => .config
  | .model | .kinematics | .grf | .activations | .momentArms | .mtLengths
  | .phases | .roles | .enriched => .work
  | .knowledgeGraph | .meshes | .musclePaths => .out

/-- The artefact's path inside its directory. A trailing `/` marks a directory. -/
def Artefact.file : Artefact → String
  | .osimModel => "Rajagopal2015.osim"
  | .geometry => "Geometry/"
  | .ikMotion => "walk/ik.mot"
  | .grfMotion => "walk/grf.mot"
  | .externalLoads => "walk/external_loads.xml"
  | .uberon => "ontology/uberon.obo"
  | .fma => "ontology/fma.owl"
  | .curatedAnatomy => "anatomy.yaml"
  | .roleThresholds => "roles.yaml"
  | .model => "model.json"
  | .kinematics => "kinematics.csv"
  | .grf => "grf.csv"
  | .activations => "activations.csv"
  | .momentArms => "moment_arms.csv"
  | .mtLengths => "mt_lengths.csv"
  | .phases => "phases.csv"
  | .roles => "roles.json"
  | .enriched => "enriched.json"
  | .knowledgeGraph => "graph.json"
  | .meshes => "meshes/index.json"
  | .musclePaths => "muscle_paths.json"

/-- The artefact's path relative to the repository root. -/
def Artefact.path (a : Artefact) : String := a.dir.root ++ a.file

/-- The artefact comes from outside the pipeline. -/
def Artefact.isSource (a : Artefact) : Bool := a.dir.isSource

/-- Distinct artefacts have distinct paths. -/
theorem Artefact.nodup_paths : (Artefact.all.map Artefact.path).Nodup := by decide

/-- The files a stage reads. -/
def Stage.reads : Stage → List Artefact
  | .loadModel => [.osimModel, .ikMotion, .grfMotion]
  | .runStaticOpt => [.osimModel, .externalLoads, .grfMotion, .kinematics]
  | .computeMomentArms => [.osimModel, .kinematics]
  | .segmentPhases => [.kinematics, .grf]
  | .labelRoles => [.activations, .momentArms, .mtLengths, .phases, .kinematics,
      .roleThresholds]
  | .enrichAnatomy => [.roles, .model, .uberon, .fma, .curatedAnatomy]
  | .exportGraph => [.enriched]
  | .exportMeshes => [.model, .geometry]
  | .exportMusclePaths => [.osimModel, .kinematics, .activations, .mtLengths]

/-- The files a stage writes. -/
def Stage.writes : Stage → List Artefact
  | .loadModel => [.model, .kinematics, .grf]
  | .runStaticOpt => [.activations]
  | .computeMomentArms => [.momentArms, .mtLengths]
  | .segmentPhases => [.phases]
  | .labelRoles => [.roles]
  | .enrichAnatomy => [.enriched]
  | .exportGraph => [.knowledgeGraph]
  | .exportMeshes => [.meshes]
  | .exportMusclePaths => [.musclePaths]

/-- Paths a stage reads, relative to the repository root. -/
def Stage.inputs (s : Stage) : List String := s.reads.map Artefact.path

/-- Paths a stage writes, relative to the repository root. -/
def Stage.outputs (s : Stage) : List String := s.writes.map Artefact.path

/-! ## Order -/

/-- The order the stages run in: Kahn's algorithm over `edges`. -/
def topoOrder : List Stage := topoSort Stage.all edges

/-- The computed order, spelled out. -/
theorem topoOrder_eq : topoOrder =
    [.loadModel, .runStaticOpt, .computeMomentArms, .segmentPhases, .labelRoles,
     .enrichAnatomy, .exportGraph, .exportMeshes, .exportMusclePaths] := by
  decide

/-- `topoOrder` lists every stage once, each after all its predecessors. -/
theorem isTopoOrder_topoOrder : IsTopoOrder graph topoOrder := by decide

/-- The stage graph is acyclic. -/
theorem acyclic : Acyclic graph := isTopoOrder_topoOrder.acyclic

/-! ## Data flow -/

/-- Every input of a stage is a source or the output of a stage upstream of it. -/
theorem inputs_available : ∀ s : Stage, ∀ a ∈ s.reads,
    a.isSource = true ∨ ∃ p, a ∈ p.writes ∧ Relation.TransGen graph.Adj p s := by
  decide

/-- Stages write derived files only: every output lands in `data/work/` or
`data/out/`. -/
theorem writes_derived : ∀ s : Stage, ∀ a ∈ s.writes, a.isSource = false := by decide

/-- Each file has at most one writer. -/
theorem writer_unique : ∀ a p q, a ∈ Stage.writes p → a ∈ Stage.writes q → p = q := by
  decide

/-- Each derived file has a writer. -/
theorem derived_written : ∀ a : Artefact, a.isSource = false → ∃ s : Stage, a ∈ s.writes := by
  decide

/-- Each source and each intermediate file feeds some stage; only the files in
`data/out/` leave the pipeline. -/
theorem read_unless_out : ∀ a : Artefact, a.dir ≠ .out → ∃ s : Stage, a ∈ s.reads := by decide

end BioMech.Pipeline
