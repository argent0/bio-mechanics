import Lake
open Lake DSL

/-! Lean package of record for the Bio-Mechanics Explorer architecture. -/

package biomech where
  leanOptions := #[⟨`autoImplicit, false⟩]

require mathlib from git
  "https://github.com/leanprover-community/mathlib4" @ "v4.35.0"

/-- Every file under `BioMech/` builds; new modules need no registration. -/
@[default_target]
lean_lib BioMech where
  globs := #[.submodules `BioMech]

/-- `lake exe gen`: writes every file under `generated/`. -/
lean_exe gen where
  root := `BioMech.Gen.Main

/-- `lake exe arch`: module map tool (`check`, `export`, `print --detail N`). -/
lean_exe arch where
  root := `BioMech.ArchMain

/-- `lake exe checkGraph FILE`: prefunctor check of a `graph.json` (workstream F). -/
lean_exe checkGraph where
  root := `BioMech.CheckGraph

/-- `lake exe conform FILE`: trace conformance against the DFAs (workstream F). -/
lean_exe conform where
  root := `BioMech.Conform
