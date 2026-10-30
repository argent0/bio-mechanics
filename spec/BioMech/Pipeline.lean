import BioMech.Acyclic

/-!
# Build pipeline

## Terms

* *Merged model*: the scaled Rajagopal model with the trunk, arm, and neck
  muscles of the upper-body models attached to its bodies (D-008).
* *Merge recipe*: the source models, the Rajagopal body each source body maps
  onto, and the neck assumption (D-010), in `pipeline/config/model.yaml`.

The offline data pipeline is a digraph of stages: an edge `a → b` means stage
`b` runs after stage `a`. Each stage is one Python script under `pipeline/`
that reads and writes the files listed here. Workstream C emits
`generated/pipeline.ninja` from this file: one build edge per stage, in
`topoOrder`, with `Stage.inputs` as dependencies and `Stage.outputs` as
targets.

Files fall into three groups, by directory (`Dir`):
* sources, maintained outside the pipeline: `data/raw/` (downloads and the
  subject-specific model and trial that `pipeline/env/make_trial.py` derives
  from them), `data/curated/` (hand-written anatomy), `pipeline/config/`
  (role thresholds and the model merge recipe);
* intermediate results in `data/work/`;
* outputs the web app loads, in `data/out/`.

The pipeline consumes one model, the merged model (`Artefact.mergedModel`),
built in two steps. First, `pipeline/env/` scales the generic model
`data/raw/rajagopal/Rajagopal2016.osim` to the walking subject
(`Artefact.scaledModel`) and runs inverse kinematics on the scaled model
(`Artefact.ikMotion`). Then stage `buildModel`, the first stage, attaches the
trunk, arm, and neck muscles that the merge recipe (`Artefact.mergeRecipe`)
names to the matching bodies of the scaled model, gives the head its own body
behind a neck joint, and writes the joint angles with the neck angles that
hold the head level in space (`Artefact.ikFull`) (D-008, D-009, D-010). Every
later stage loads the merged model and those joint angles, so activations,
moment arms, muscle paths, and bone meshes all share the subject's segment
lengths and one set of coordinates.

Theorems: the stage graph is acyclic and `topoOrder` is a topological order of
it; every input of a stage is a source or an output of a stage upstream of it;
each derived file has exactly one writer; `buildModel` runs upstream of every
other stage and is the one stage that reads the scaled model, the
inverse-kinematics motion, the merge recipe, and the files the recipe names
(the meshes of `geometry` aside, which `exportMeshes` reads too).
-/

namespace BioMech.Pipeline

/-- Pipeline stages, in handover order, with the model merge first. -/
inductive Stage
  /-- Merge the trunk, arm, and neck muscles of the upper-body models onto the
  scaled Rajagopal model, give the head its own body behind a neck joint, and
  add the neck angles that hold the head level in space to the joint angles
  (D-008, D-009, D-010). -/
  | buildModel
  /-- Load the merged model and the walking trial with the OpenSim API. -/
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
  /-- Convert the model's bone geometry to glTF, each mesh multiplied by its
  scale factors from the merged model. -/
  | exportMeshes
  /-- Write muscle path points per frame for the tube renderer, with the
  bounds of the stride the knowledge graph describes. -/
  | exportMusclePaths
  /-- Write each muscle's moment about each joint coordinate, and the
  coordinate's angle, per frame, for the dynamics panel. -/
  | exportDynamics
  deriving DecidableEq, Repr, Inhabited

/-- Every stage, in declaration order. -/
def Stage.all : List Stage :=
  [.buildModel, .loadModel, .runStaticOpt, .computeMomentArms, .segmentPhases, .labelRoles,
   .enrichAnatomy, .exportGraph, .exportMeshes, .exportMusclePaths, .exportDynamics]

/-- `Stage.all` lists every stage. -/
theorem Stage.mem_all (s : Stage) : s ∈ Stage.all := by cases s <;> decide

/-- `Stage.all` lists each stage once. -/
theorem Stage.nodup_all : Stage.all.Nodup := by decide

instance : Fintype Stage := ⟨⟨Stage.all, Multiset.coe_nodup.mpr Stage.nodup_all⟩, Stage.mem_all⟩

/-- Stage name as written in Lean, e.g. `loadModel`. -/
def Stage.name : Stage → String
  | .buildModel => "buildModel"
  | .loadModel => "loadModel"
  | .runStaticOpt => "runStaticOpt"
  | .computeMomentArms => "computeMomentArms"
  | .segmentPhases => "segmentPhases"
  | .labelRoles => "labelRoles"
  | .enrichAnatomy => "enrichAnatomy"
  | .exportGraph => "exportGraph"
  | .exportMeshes => "exportMeshes"
  | .exportMusclePaths => "exportMusclePaths"
  | .exportDynamics => "exportDynamics"

/-- The Python script that runs the stage, relative to the repository root. -/
def Stage.script : Stage → String
  | .buildModel => "pipeline/build_model.py"
  | .loadModel => "pipeline/load_model.py"
  | .runStaticOpt => "pipeline/static_opt.py"
  | .computeMomentArms => "pipeline/moment_arms.py"
  | .segmentPhases => "pipeline/segment_phases.py"
  | .labelRoles => "pipeline/label_roles.py"
  | .enrichAnatomy => "pipeline/enrich_anatomy.py"
  | .exportGraph => "pipeline/export_graph.py"
  | .exportMeshes => "pipeline/export_meshes.py"
  | .exportMusclePaths => "pipeline/export_muscle_paths.py"
  | .exportDynamics => "pipeline/export_dynamics.py"

/-- Stage order: `a → b` means `b` runs after `a`. -/
def edges : List (Stage × Stage) :=
  [(.buildModel, .loadModel), (.loadModel, .runStaticOpt), (.runStaticOpt, .computeMomentArms),
   (.computeMomentArms, .segmentPhases), (.segmentPhases, .labelRoles),
   (.labelRoles, .enrichAnatomy), (.enrichAnatomy, .exportGraph),
   (.loadModel, .exportMeshes),
   (.computeMomentArms, .exportMusclePaths), (.runStaticOpt, .exportMusclePaths),
   (.segmentPhases, .exportMusclePaths), (.segmentPhases, .exportDynamics)]

/-- The stage digraph: adjacency is membership in `edges`. -/
abbrev graph : Digraph Stage := ofEdges edges

/-! ## Files -/

/-- The directory a pipeline file lives in. -/
inductive Dir
  /-- Downloads (OpenSim models, walking trial, ontology subsets) and the scaled
  model and joint angles derived from them in `pipeline/env/`. -/
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
  /-- The Rajagopal full-body model scaled to the walking subject: the base
  model `buildModel` merges the upper-body muscles onto. -/
  | scaledModel
  /-- The subject's scale factors per body, from the OpenSim ScaleTool:
  `buildModel` multiplies each merged point by its body's factors. -/
  | scaleSet
  /-- Joint coordinates of the standing calibration pose (the static pose):
  the head orientation that the neck angles hold (D-010). -/
  | staticPose
  /-- The bone surface meshes (`.vtp`) the model refers to, at generic size;
  `buildModel` places the neck model on `hat_skull.vtp` among them. -/
  | geometry
  /-- Joint coordinates per frame of the walking trial, from inverse kinematics
  on `scaledModel`; `buildModel` adds the neck angles to them. -/
  | ikMotion
  /-- Ground reaction forces and centres of pressure per frame of the trial. -/
  | grfMotion
  /-- OpenSim external loads: each foot's ground reaction force on `calcn_r`
  and `calcn_l`, read from `grfMotion`. -/
  | externalLoads
  /-- The full-body lumbar spine model of Raabe and Chaudhari (2016, FBLS):
  the lumbar vertebrae and the trunk and latissimus muscles (D-011). -/
  | fblsModel
  /-- The Stanford VA upper-limb model of Holzbaur (2005), right arm: the arm
  muscles, mirrored for the left arm. -/
  | holzbaurModel
  /-- The HYOID 1.2 head and neck model of Mortensen (2018): the cervical
  vertebrae, the skull, and the neck muscles (D-009). -/
  | mortensenModel
  /-- The skull mesh of `mortensenModel`: its bounding box, laid on that of
  Rajagopal's `hat_skull.vtp`, places the neck model on the torso. -/
  | mortensenSkull
  /-- Uberon subset: anatomy terms and part-of relations. -/
  | uberon
  /-- FMA subset: attachments and innervation. -/
  | fma
  /-- Hand-curated common names, attachments, and innervation. -/
  | curatedAnatomy
  /-- Role-classification thresholds. -/
  | roleThresholds
  /-- The merge recipe: the source models, the Rajagopal body each source body
  maps onto, the paths of the scale set, static pose, and meshes, and the
  neck assumption (D-008 to D-011). Each file it names is a read of
  `buildModel`. -/
  | mergeRecipe
  /-- The scaled Rajagopal model with the trunk, arm, and neck muscles merged
  in and the head on its own body behind a neck joint: the one model every
  stage after `buildModel` loads. -/
  | mergedModel
  /-- `ikMotion`'s joint coordinates plus, per frame, the neck angles that
  cancel the torso's rotation in the ground frame, so the head keeps its
  static-pose orientation (D-010). -/
  | ikFull
  /-- Bodies (with their mesh files), joints, coordinates, and muscles (with
  maximum isometric forces) of the model, under their OpenSim names. -/
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
  /-- Muscle path points, activation, and lengthening velocity per frame, and
  the start and end times of the stride. -/
  | musclePaths
  /-- Per frame: each muscle's moment about each labelled joint coordinate,
  and the coordinate's angle. -/
  | dynamics
  deriving DecidableEq, Repr, Inhabited

/-- Every artefact, in declaration order. -/
def Artefact.all : List Artefact :=
  [.scaledModel, .scaleSet, .staticPose, .geometry, .ikMotion, .grfMotion, .externalLoads,
   .fblsModel, .holzbaurModel, .mortensenModel, .mortensenSkull, .uberon, .fma,
   .curatedAnatomy, .roleThresholds, .mergeRecipe,
   .mergedModel, .ikFull, .model, .kinematics, .grf, .activations, .momentArms, .mtLengths, .phases,
   .roles, .enriched,
   .knowledgeGraph, .meshes, .musclePaths, .dynamics]

/-- `Artefact.all` lists every artefact. -/
theorem Artefact.mem_all (a : Artefact) : a ∈ Artefact.all := by cases a <;> decide

/-- `Artefact.all` lists each artefact once. -/
theorem Artefact.nodup_all : Artefact.all.Nodup := by decide

instance : Fintype Artefact :=
  ⟨⟨Artefact.all, Multiset.coe_nodup.mpr Artefact.nodup_all⟩, Artefact.mem_all⟩

/-- The directory an artefact lives in. -/
def Artefact.dir : Artefact → Dir
  | .scaledModel | .scaleSet | .staticPose | .geometry | .ikMotion | .grfMotion
  | .externalLoads | .fblsModel | .holzbaurModel | .mortensenModel | .mortensenSkull
  | .uberon | .fma => .raw
  | .curatedAnatomy => .curated
  | .roleThresholds | .mergeRecipe => .config
  | .mergedModel | .ikFull | .model | .kinematics | .grf | .activations | .momentArms | .mtLengths
  | .phases | .roles | .enriched => .work
  | .knowledgeGraph | .meshes | .musclePaths | .dynamics => .out

/-- The artefact's path inside its directory. A trailing `/` marks a directory. -/
def Artefact.file : Artefact → String
  | .scaledModel => "rajagopal/walk_pipeline/Scale/subject_scaled_walk.osim"
  | .scaleSet => "rajagopal/walk_pipeline/Scale/scaleSet_applied_walk.xml"
  | .staticPose => "rajagopal/walk_pipeline/Scale/scale_output_walk.mot"
  | .geometry => "rajagopal/Geometry/"
  | .ikMotion => "rajagopal/walk_pipeline/IK/results_walk/ik_output_walk.mot"
  | .grfMotion => "rajagopal/walk_pipeline/ExpData/grf_walk.mot"
  | .externalLoads => "rajagopal/walk_pipeline/ID/grf_walk.xml"
  | .fblsModel => "fbls/FBLSmodel.osim"
  | .holzbaurModel => "holzbaur/Stanford_VA_Upper_Limb_original.osim"
  | .mortensenModel => "mortensen/HYOID_1.2_ScaledStrenght_UpdatedInertia.osim"
  | .mortensenSkull => "mortensen/Geometry/skull.vtp"
  | .uberon => "ontology/uberon.obo"
  | .fma => "ontology/fma.owl"
  | .curatedAnatomy => "anatomy.yaml"
  | .roleThresholds => "roles.yaml"
  | .mergeRecipe => "model.yaml"
  | .mergedModel => "model.osim"
  | .ikFull => "ik_full.mot"
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
  | .dynamics => "dynamics.json"

/-- The artefact's path relative to the repository root. -/
def Artefact.path (a : Artefact) : String := a.dir.root ++ a.file

/-- The artefact comes from outside the pipeline. -/
def Artefact.isSource (a : Artefact) : Bool := a.dir.isSource

/-- Distinct artefacts have distinct paths. -/
theorem Artefact.nodup_paths : (Artefact.all.map Artefact.path).Nodup := by decide

/-- The files a stage reads. Every file a stage's script opens appears here,
so ninja reruns the stage whenever one of them changes. Reads whose reason is
less evident from the stage's purpose:
* `buildModel` reads the files the merge recipe names: the three source
  models, the scale set, the static pose, and two meshes for placing the neck
  model (`mortensenSkull` and `hat_skull.vtp` in `geometry`). `ikMotion`
  serves it twice: the right arm's mean posture over the trial fixes the arm
  muscles' via points, and the torso's rotation in the ground frame at each
  frame gives the neck angles that cancel it (D-010).
* `segmentPhases` reads `mergedModel`: OpenSim poses the model at each frame
  of `kinematics` and reports the foot and leg marker positions that locate
  the gait events.
* `labelRoles` reads `model`: each muscle's maximum isometric force scales its
  activation into a force, and so into a joint moment.
* `exportMeshes` reads `mergedModel`: each mesh's scale factors live there,
  and `model` lists the mesh files only.
* `exportMusclePaths` reads `phases`: the gait events there give the stride
  bounds, the opening and closing right initial contacts of the stride whose
  phase percentages `graph.json` carries, so the viewer plays that stride.
* `exportDynamics` reads `curatedAnatomy`: it names the joint action each
  direction of a coordinate is, and `mtLengths` only because `labelRoles`'s
  trial reader loads it alongside the moment arms. -/
def Stage.reads : Stage → List Artefact
  | .buildModel => [.scaledModel, .ikMotion, .mergeRecipe, .scaleSet, .staticPose,
      .fblsModel, .holzbaurModel, .mortensenModel, .mortensenSkull, .geometry]
  | .loadModel => [.mergedModel, .ikFull, .grfMotion]
  | .runStaticOpt => [.mergedModel, .externalLoads, .grfMotion, .kinematics]
  | .computeMomentArms => [.mergedModel, .kinematics]
  | .segmentPhases => [.mergedModel, .kinematics, .grf]
  | .labelRoles => [.model, .activations, .momentArms, .mtLengths, .phases, .kinematics,
      .roleThresholds]
  | .enrichAnatomy => [.roles, .model, .uberon, .fma, .curatedAnatomy]
  | .exportGraph => [.enriched]
  | .exportMeshes => [.mergedModel, .model, .geometry]
  | .exportMusclePaths => [.mergedModel, .kinematics, .activations, .mtLengths, .phases]
  | .exportDynamics => [.model, .kinematics, .activations, .momentArms, .mtLengths, .phases,
      .roleThresholds, .curatedAnatomy]

/-- The files a stage writes. -/
def Stage.writes : Stage → List Artefact
  | .buildModel => [.mergedModel, .ikFull]
  | .loadModel => [.model, .kinematics, .grf]
  | .runStaticOpt => [.activations]
  | .computeMomentArms => [.momentArms, .mtLengths]
  | .segmentPhases => [.phases]
  | .labelRoles => [.roles]
  | .enrichAnatomy => [.enriched]
  | .exportGraph => [.knowledgeGraph]
  | .exportMeshes => [.meshes]
  | .exportMusclePaths => [.musclePaths]
  | .exportDynamics => [.dynamics]

/-- Paths a stage reads, relative to the repository root. -/
def Stage.inputs (s : Stage) : List String := s.reads.map Artefact.path

/-- Paths a stage writes, relative to the repository root. -/
def Stage.outputs (s : Stage) : List String := s.writes.map Artefact.path

/-! ## Order -/

/-- The order the stages run in: Kahn's algorithm over `edges`. -/
def topoOrder : List Stage := topoSort Stage.all edges

/-- The computed order, spelled out. -/
theorem topoOrder_eq : topoOrder =
    [.buildModel, .loadModel, .runStaticOpt, .computeMomentArms, .segmentPhases, .labelRoles,
     .enrichAnatomy, .exportGraph, .exportMeshes, .exportMusclePaths, .exportDynamics] := by
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

/-! ## The model merge -/

/-- `buildModel` runs upstream of every other stage. -/
theorem buildModel_upstream : ∀ s : Stage, s ≠ .buildModel →
    Relation.TransGen graph.Adj .buildModel s := by
  decide

/-- `buildModel` is the one stage that reads the scaled model or the
inverse-kinematics motion; every other stage loads the merged model and the
joint angles that carry the neck angles (D-008, D-010). -/
theorem buildModel_sole_reader_of_scaled : ∀ s : Stage,
    (.scaledModel ∈ s.reads ∨ .ikMotion ∈ s.reads) ↔ s = .buildModel := by
  decide

/-- The merge recipe and the files it names, the meshes of `geometry` aside,
feed `buildModel` alone. -/
theorem merge_sources_feed_buildModel : ∀ s : Stage, ∀ a ∈ [Artefact.mergeRecipe,
    .scaleSet, .staticPose, .fblsModel, .holzbaurModel, .mortensenModel, .mortensenSkull],
    a ∈ s.reads ↔ s = .buildModel := by
  decide

end BioMech.Pipeline
