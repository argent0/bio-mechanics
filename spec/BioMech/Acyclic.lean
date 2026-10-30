import Mathlib.Combinatorics.Digraph.Basic
import Mathlib.Logic.Relation

/-!
# Acyclicity, reachability, and topological orders

Shared graph definitions for the build pipeline (`BioMech.Pipeline`) and the
front-end components (`BioMech.Components`). Both graphs are plain edge lists
over a small enumeration; `ofEdges` turns such a list into a Mathlib `Digraph`.

Each property below has a decidable form, so every concrete theorem in the two
graph files is a `decide` over a handful of vertices and edges.

* `Acyclic G`: the transitive closure of `G.Adj` is irreflexive. Three routes
  prove it: a rank that grows along every edge (`acyclic_of_rank`), a
  topological order (`IsTopoOrder.acyclic`), or `decide` through reachability.
* `reachable es u`: the vertices `u` reaches along one or more edges, computed
  as a finite closure. `transGen_iff_mem_reachable` equates it with
  `Relation.TransGen`, which makes `TransGen` decidable on edge-list digraphs.
* `deleteVertex G x` and `ReachesOnlyVia G u x v`: layering rules of the form
  "`u` reaches `v` only through `x`".
* `IsTopoOrder G l` and `topoSort vs es`: topological orders and Kahn's
  algorithm.
-/

namespace BioMech

universe u
variable {V : Type u}

/-- A digraph is acyclic when the transitive closure of its adjacency is
irreflexive: every path of one or more edges ends at a vertex other than its
start. -/
def Acyclic (G : Digraph V) : Prop := ∀ v, ¬ Relation.TransGen G.Adj v v

/-! ## Ranks -/

/-- A rank that grows along every edge grows strictly along every path. -/
theorem rank_lt_of_transGen {G : Digraph V} (r : V → ℕ)
    (h : ∀ u v, G.Adj u v → r u < r v) {u v : V}
    (huv : Relation.TransGen G.Adj u v) : r u < r v := by
  induction huv with
  | single hab => exact h _ _ hab
  | tail _ hbc ih => exact ih.trans (h _ _ hbc)

/-- A rank that grows strictly along every edge proves acyclicity. -/
theorem acyclic_of_rank {G : Digraph V} (r : V → ℕ)
    (h : ∀ u v, G.Adj u v → r u < r v) : Acyclic G :=
  fun _ hv => lt_irrefl _ (rank_lt_of_transGen r h hv)

/-! ## Edge-list digraphs -/

/-- The digraph whose edges are exactly the pairs listed in `es`. -/
def ofEdges (es : List (V × V)) : Digraph V where
  Adj a b := (a, b) ∈ es

/-- The rank lemma in list form: the check runs over the listed edges only. -/
theorem acyclic_ofEdges_of_rank (es : List (V × V)) (r : V → ℕ)
    (h : ∀ e ∈ es, r e.1 < r e.2) : Acyclic (ofEdges es) :=
  acyclic_of_rank r fun a b hab => h (a, b) hab

/-- `G` with the vertex `x` removed: the edges of `G` whose two ends differ
from `x`. -/
def deleteVertex (G : Digraph V) (x : V) : Digraph V where
  Adj a b := G.Adj a b ∧ a ≠ x ∧ b ≠ x

/-- `u` reaches `v` in `G`, and every path from `u` to `v` passes through `x`:
deleting `x` disconnects `u` from `v`. -/
structure ReachesOnlyVia (G : Digraph V) (u x v : V) : Prop where
  /-- Some path leads from `u` to `v`. -/
  reaches : Relation.TransGen G.Adj u v
  /-- Every path from `u` to `v` visits `x`. -/
  cut : ¬ Relation.TransGen (deleteVertex G x).Adj u v

section DecEq
variable [DecidableEq V]

instance (es : List (V × V)) : DecidableRel (ofEdges es).Adj :=
  fun a b => inferInstanceAs (Decidable ((a, b) ∈ es))

/-- Deleting a vertex from an edge-list digraph filters its edge list. -/
theorem deleteVertex_ofEdges (es : List (V × V)) (x : V) :
    deleteVertex (ofEdges es) x = ofEdges (es.filter fun e => e.1 ≠ x ∧ e.2 ≠ x) := by
  ext a b
  simp [deleteVertex, ofEdges, List.mem_filter]

/-! ## Reachability as a finite closure -/

namespace Reach

/-- The targets of the edges of `es` that start in `S`: the one-step
successors of `S`. -/
def image (es : List (V × V)) (S : List V) : List V :=
  (es.filter fun e => e.1 ∈ S).map Prod.snd

theorem mem_image {es : List (V × V)} {S : List V} {w : V} :
    w ∈ image es S ↔ ∃ v ∈ S, (v, w) ∈ es := by
  simp only [image, List.mem_map, List.mem_filter, decide_eq_true_eq, Prod.exists]
  constructor
  · rintro ⟨a, b, ⟨hab, ha⟩, rfl⟩
    exact ⟨a, ha, hab⟩
  · rintro ⟨a, ha, hab⟩
    exact ⟨a, w, ⟨hab, ha⟩, rfl⟩

/-- `n` rounds of closure: each round adds the successors of the current set. -/
def closeN (es : List (V × V)) : ℕ → List V → List V
  | 0, S => S
  | n + 1, S => closeN es n (S ∪ image es S)

/-- `S` is closed under `es`: every edge that starts in `S` ends in `S`. -/
def Closed (es : List (V × V)) (S : List V) : Prop :=
  ∀ v w, v ∈ S → (v, w) ∈ es → w ∈ S

/-- The edge targets outside `S`. Each round of closure on a set that is still
open lowers this count. -/
def missing (es : List (V × V)) (S : List V) : ℕ :=
  ((es.map Prod.snd).filter fun w => w ∉ S).length

variable {es : List (V × V)}

theorem subset_closeN : ∀ (n : ℕ) (S : List V), ∀ v ∈ S, v ∈ closeN es n S
  | 0, _, _, hv => hv
  | n + 1, _, v, hv => subset_closeN n _ v (List.mem_union_iff.mpr (Or.inl hv))

/-- Every vertex the closure adds is reachable from `u`, given a start set
reachable from `u`. -/
theorem closeN_sound (u : V) : ∀ (n : ℕ) (S : List V),
    (∀ s ∈ S, Relation.TransGen (ofEdges es).Adj u s) →
    ∀ v ∈ closeN es n S, Relation.TransGen (ofEdges es).Adj u v
  | 0, _, hS, v, hv => hS v hv
  | n + 1, S, hS, v, hv => by
    refine closeN_sound u n _ (fun s hs => ?_) v hv
    rcases List.mem_union_iff.mp hs with hs | hs
    · exact hS s hs
    · obtain ⟨t, ht, hts⟩ := mem_image.mp hs
      exact (hS t ht).tail hts

theorem closed_union_image {S : List V} (h : Closed es S) :
    Closed es (S ∪ image es S) := by
  intro v w hv hvw
  refine List.mem_union_iff.mpr (Or.inl ?_)
  rcases List.mem_union_iff.mp hv with hv | hv
  · exact h v w hv hvw
  · obtain ⟨t, ht, htv⟩ := mem_image.mp hv
    exact h v w (h t v ht htv) hvw

theorem closed_closeN_of_closed : ∀ (n : ℕ) {S : List V},
    Closed es S → Closed es (closeN es n S)
  | 0, _, h => h
  | n + 1, _, h => closed_closeN_of_closed n (closed_union_image h)

/-- A round of closure on an open set adds an edge target that was missing. -/
theorem missing_union_lt {S : List V} (h : ¬ Closed es S) :
    missing es (S ∪ image es S) < missing es S := by
  simp only [Closed, not_forall] at h
  obtain ⟨v, w, hv, hvw, hw⟩ := h
  have hsub : ((es.map Prod.snd).filter fun t => t ∉ S ∪ image es S).Sublist
      ((es.map Prod.snd).filter fun t => t ∉ S) := by
    apply List.monotone_filter_right
    intro t ht
    simp only [decide_eq_true_eq, List.mem_union_iff, not_or] at ht ⊢
    exact ht.1
  refine lt_of_le_of_ne hsub.length_le fun heq => ?_
  have hmem : w ∈ (es.map Prod.snd).filter fun t => t ∉ S := by
    simp only [List.mem_filter, List.mem_map, decide_eq_true_eq, Prod.exists]
    exact ⟨⟨v, w, hvw, rfl⟩, hw⟩
  rw [← hsub.eq_of_length heq] at hmem
  simp only [List.mem_filter, decide_eq_true_eq, List.mem_union_iff, not_or] at hmem
  exact hmem.2.2 (mem_image.mpr ⟨v, hv, hvw⟩)

theorem closed_closeN : ∀ (n : ℕ) (S : List V), missing es S ≤ n →
    Closed es (closeN es n S)
  | 0, S, h => by
    intro v w hv hvw
    by_contra hw
    have hmem : w ∈ (es.map Prod.snd).filter fun t => t ∉ S := by
      simp only [List.mem_filter, List.mem_map, decide_eq_true_eq, Prod.exists]
      exact ⟨⟨v, w, hvw, rfl⟩, hw⟩
    have := List.length_pos_of_mem hmem
    simp only [missing] at h
    omega
  | n + 1, S, h => by
    by_cases hc : Closed es S
    · exact closed_closeN_of_closed n (closed_union_image hc)
    · exact closed_closeN n _ (by have := missing_union_lt hc; omega)

end Reach

/-- The vertices that `u` reaches along one or more edges of `es`: the closure
of the successors of `u`. `es.length` rounds reach the fixed point
(`closed_reachable`). -/
def reachable (es : List (V × V)) (u : V) : List V :=
  Reach.closeN es es.length (Reach.image es [u])

open Reach

variable {es : List (V × V)}

/-- `es.length` rounds of closure reach a closed set. -/
theorem closed_reachable (u : V) : Closed es (reachable es u) :=
  closed_closeN _ _ ((List.length_filter_le _ _).trans (List.length_map _).le)

/-- Reachability computed by closure agrees with the transitive closure of the
adjacency. -/
theorem transGen_iff_mem_reachable {u v : V} :
    Relation.TransGen (ofEdges es).Adj u v ↔ v ∈ reachable es u := by
  constructor
  · intro h
    induction h with
    | single hab =>
      exact subset_closeN _ _ _ (mem_image.mpr ⟨u, List.mem_singleton_self u, hab⟩)
    | tail _ hbc ih => exact closed_reachable u _ _ ih hbc
  · refine closeN_sound u _ _ (fun s hs => ?_) v
    obtain ⟨t, ht, hts⟩ := mem_image.mp hs
    rw [List.mem_singleton.mp ht] at hts
    exact Relation.TransGen.single hts

instance (es : List (V × V)) : DecidableRel (Relation.TransGen (ofEdges es).Adj) :=
  fun _ _ => decidable_of_iff _ transGen_iff_mem_reachable.symm

instance (es : List (V × V)) (x : V) :
    DecidableRel (Relation.TransGen (deleteVertex (ofEdges es) x).Adj) :=
  fun a b => decidable_of_iff
    (Relation.TransGen (ofEdges (es.filter fun e => e.1 ≠ x ∧ e.2 ≠ x)).Adj a b)
    (by rw [deleteVertex_ofEdges])

instance [Fintype V] (G : Digraph V) [DecidableRel (Relation.TransGen G.Adj)] :
    Decidable (Acyclic G) :=
  inferInstanceAs (Decidable (∀ v, ¬ Relation.TransGen G.Adj v v))

instance (G : Digraph V) (u x v : V) [Decidable (Relation.TransGen G.Adj u v)]
    [Decidable (Relation.TransGen (deleteVertex G x).Adj u v)] :
    Decidable (ReachesOnlyVia G u x v) :=
  decidable_of_iff (Relation.TransGen G.Adj u v ∧ ¬ Relation.TransGen (deleteVertex G x).Adj u v)
    ⟨fun ⟨h₁, h₂⟩ => ⟨h₁, h₂⟩, fun ⟨h₁, h₂⟩ => ⟨h₁, h₂⟩⟩

/-! ## Topological orders -/

/-- `l` is a topological order of `G`: it lists every vertex exactly once, and
every edge points from an earlier position to a later one. -/
structure IsTopoOrder (G : Digraph V) (l : List V) : Prop where
  /-- Each vertex appears at most once. -/
  nodup : l.Nodup
  /-- Each vertex appears. -/
  complete : ∀ v, v ∈ l
  /-- Every edge points forward. -/
  forward : ∀ a b, G.Adj a b → l.idxOf a < l.idxOf b

instance [Fintype V] (G : Digraph V) [DecidableRel G.Adj] (l : List V) :
    Decidable (IsTopoOrder G l) :=
  decidable_of_iff (l.Nodup ∧ (∀ v, v ∈ l) ∧ ∀ a b, G.Adj a b → l.idxOf a < l.idxOf b)
    ⟨fun ⟨h₁, h₂, h₃⟩ => ⟨h₁, h₂, h₃⟩, fun ⟨h₁, h₂, h₃⟩ => ⟨h₁, h₂, h₃⟩⟩

/-- A digraph with a topological order is acyclic: positions in the order form
a rank. -/
theorem IsTopoOrder.acyclic {G : Digraph V} {l : List V} (h : IsTopoOrder G l) :
    Acyclic G :=
  acyclic_of_rank _ h.forward

/-- Kahn's algorithm with fuel `n`. Each round emits the first vertex of `rest`
whose incoming edges all start outside `rest`, then removes it. On a cycle the
output stops short of the full vertex list, and `IsTopoOrder` then fails by
`decide`. -/
def kahn (es : List (V × V)) : ℕ → List V → List V
  | 0, _ => []
  | n + 1, rest =>
    match rest.find? (fun v => es.all fun e => !(e.2 == v && rest.contains e.1)) with
    | some v => v :: kahn es n (rest.erase v)
    | none => []

/-- Topological sort of the vertices `vs` under the edges `es`: Kahn's
algorithm with one round per vertex. Ties go to the vertex listed first in
`vs`. -/
def topoSort (vs : List V) (es : List (V × V)) : List V :=
  kahn es vs.length vs

end DecEq

end BioMech
