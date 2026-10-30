import Mathlib.Combinatorics.Quiver.Basic
import BioMech.GaitFsm

/-!
# Knowledge-graph schema (contract C1)

The schema of the knowledge graph is a quiver: node kinds are its vertices and
the allowed relations are its arrows. A data graph is well typed when it carries
a prefunctor into this quiver (checked by `lake exe checkGraph`).

Node and edge attributes are Lean structures. `lake exe gen` reads these
declarations by reflection and emits `generated/ts/types.ts` and
`generated/py/schema.py`, so this file is the single source for the
`graph.json` shape (contract C3).

Field types the emitters understand: `String`, `Float`, `Nat`, `Int`, `Bool`,
`Option α`, `Array α`, and enumerations from `BioMech` and its namespaces
(inductives whose constructors take no arguments), e.g. `Role` here and
`Gait.GaitEvent` from `BioMech.GaitFsm`.
-/

namespace BioMech

/-- Node kinds: the vertices of the schema quiver. -/
inductive Kind
  | bone | joint | muscle | muscleGroup | ligament | nerve
  | movement | phase | jointAction
  deriving DecidableEq, Repr, Inhabited

/-- Allowed relations: the arrows of the schema quiver, each typed by the kinds
of its source and target. -/
inductive SchemaArrow : Kind → Kind → Type
  | origin       : SchemaArrow .muscle .bone
  | insertion    : SchemaArrow .muscle .bone
  | crosses      : SchemaArrow .muscle .joint
  | partOf       : SchemaArrow .muscle .muscleGroup
  | innervatedBy : SchemaArrow .muscle .nerve
  | stabilises   : SchemaArrow .ligament .joint
  | articulates  : SchemaArrow .joint .bone
  | hasPhase     : SchemaArrow .movement .phase
  | precedes     : SchemaArrow .phase .phase
  | involves     : SchemaArrow .phase .jointAction
  | actionAt     : SchemaArrow .jointAction .joint
  | drivenBy     : SchemaArrow .jointAction .muscle
  deriving DecidableEq, Repr

instance : Quiver Kind := ⟨SchemaArrow⟩

/-- Every arrow of the schema quiver, with its source and target kinds. -/
def SchemaArrow.all : List (Σ a b : Kind, SchemaArrow a b) :=
  [⟨_, _, .origin⟩, ⟨_, _, .insertion⟩, ⟨_, _, .crosses⟩, ⟨_, _, .partOf⟩,
   ⟨_, _, .innervatedBy⟩, ⟨_, _, .stabilises⟩, ⟨_, _, .articulates⟩,
   ⟨_, _, .hasPhase⟩, ⟨_, _, .precedes⟩, ⟨_, _, .involves⟩, ⟨_, _, .actionAt⟩, ⟨_, _, .drivenBy⟩]

/-- `SchemaArrow.all` lists every arrow. -/
theorem SchemaArrow.mem_all {a b : Kind} (e : SchemaArrow a b) :
    (⟨a, b, e⟩ : Σ a b : Kind, SchemaArrow a b) ∈ SchemaArrow.all := by
  cases e <;> simp [SchemaArrow.all]

/-! ## Attribute enumerations -/

/-- The role a muscle plays in a joint action during one phase. -/
inductive Role
  | mainMover | helper | stabiliser | antagonist
  deriving DecidableEq, Repr, Inhabited

/-- The kind of work a muscle does: shortening, lengthening under load
(braking), or holding length. -/
inductive Contraction
  | concentric | eccentric | isometric
  deriving DecidableEq, Repr, Inhabited

/-- The side of the body a node belongs to; `midline` for unpaired parts. -/
inductive Side
  | left | right | midline
  deriving DecidableEq, Repr, Inhabited

/-! ## Node attributes -/

/-- Attributes every node carries. `id` is unique within one graph. -/
structure NodeAttrs where
  /-- Unique node identifier, e.g. `muscle:glmed1_r`. -/
  id : String
  /-- The node's vertex in the schema quiver. -/
  kind : Kind
  /-- Anatomical name, e.g. "gluteus medius". -/
  name : String
  /-- Common name, e.g. "side glute". -/
  commonName : Option String
  /-- Body side. -/
  side : Side
  /-- Foundational Model of Anatomy identifier, e.g. `FMA:22314`. -/
  fmaId : Option String
  /-- Uberon identifier, e.g. `UBERON:0001367`. -/
  uberonId : Option String
  /-- Name of the element in the OpenSim model (muscle, body, or joint). -/
  opensimName : Option String

/-! ## Edge attributes

An arrow listed in `edgeAttrs` carries the named structure's fields on every
edge of that relation; every other arrow carries only the common edge fields
(`source`, `target`, `relation`).
-/

/-- Attributes of `crosses` (muscle → joint): the lever the muscle has at the
joint, summarised over the movement. -/
structure CrossesAttrs where
  /-- OpenSim coordinate the moment arm is measured about, e.g. `knee_angle_r`. -/
  coordinate : String
  /-- Moment arm in metres, sampled at evenly spaced points across the movement
  cycle, first and last sample at its boundaries. -/
  momentArm : Array Float

/-- Attributes of `drivenBy` (joint action → muscle), per phase. -/
structure DrivenByAttrs where
  /-- Identifier of the phase node these values belong to. -/
  phase : String
  /-- The muscle's role in the joint action during the phase. -/
  role : Role
  /-- Work type during the phase. -/
  contraction : Contraction
  /-- Peak activation in the phase, in 0–1. -/
  peakActivation : Float
  /-- Activation in 0–1, sampled at evenly spaced points across the phase. -/
  activation : Array Float
  /-- Moment arm in metres about the joint action's coordinate, sampled at the
  same points as `activation`. -/
  momentArm : Array Float

/-- Attributes of `involves` (phase → joint action). -/
structure InvolvesAttrs where
  /-- Joint angle change across the phase, in degrees. -/
  rangeDeg : Float

/-- Attributes of `hasPhase` (movement → phase): where the phase sits in the cycle. -/
structure HasPhaseAttrs where
  /-- Position in the cycle, starting at 0. -/
  order : Nat
  /-- Start of the phase, in percent of the cycle. -/
  startPct : Float
  /-- End of the phase, in percent of the cycle. -/
  endPct : Float
  /-- The period the phase belongs to (`Gait.GaitPhase.stance`, `Gait.GaitPhase.swing`). -/
  period : Gait.Period

/-- Attributes of `precedes` (phase → phase): the next phase of the cycle, one
edge per row of `Gait.transitions`. The edges form one loop through the seven
phases, from terminal swing back to loading response. -/
structure PrecedesAttrs where
  /-- The gait event that ends the source phase and opens the target phase. -/
  event : Gait.GaitEvent

open Lean in
/-- Which arrows carry an attribute structure. The double-backtick names are
checked by the compiler, so a renamed constructor or structure breaks the build. -/
def edgeAttrs : List (Name × Name) :=
  [(``SchemaArrow.crosses, ``CrossesAttrs),
   (``SchemaArrow.drivenBy, ``DrivenByAttrs),
   (``SchemaArrow.involves, ``InvolvesAttrs),
   (``SchemaArrow.hasPhase, ``HasPhaseAttrs),
   (``SchemaArrow.precedes, ``PrecedesAttrs)]

/-- Version of the `graph.json` shape. Bump on any change to this file's
structures. -/
def schemaVersion : Nat := 3

end BioMech
