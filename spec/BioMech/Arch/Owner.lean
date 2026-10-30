import BioMech.Architecture

/-!
# Path ownership

Resolves which module owns a file. A pattern ending in `/` owns its directory
tree; a pattern with `*` matches within one segment; any other pattern is one
file. The longest matching pattern wins; two modules tying on a file is an error.
-/

namespace BioMech.Arch

/-- Glob match of one path segment, where `*` matches any run of characters. -/
partial def globSeg : List Char → List Char → Bool
  | [], [] => true
  | '*' :: ps, s => globSeg ps s || (match s with | [] => false | _ :: s' => globSeg ('*' :: ps) s')
  | p :: ps, c :: s => p == c && globSeg ps s
  | _, _ => false

/-- Whether `pat` matches the repository-relative path `file`. -/
def patternMatches (pat file : String) : Bool :=
  if pat.endsWith "/" then file.startsWith pat
  else if pat.contains '*' then
    let ps := pat.splitOn "/"
    let fs := file.splitOn "/"
    ps.length == fs.length && (ps.zip fs).all fun (p, f) => globSeg p.toList f.toList
  else pat == file

/-- Every module whose most specific matching pattern for `file` has the
greatest length, with that length. -/
def owners (file : String) : List ModuleId × Nat :=
  let hits := modules.filterMap fun m =>
    let lens := (m.paths.filter (patternMatches · file)).map (·.length)
    lens.max?.map (m.id, ·)
  match hits.map (·.2) |>.max? with
  | none => ([], 0)
  | some best => ((hits.filter (·.2 == best)).map (·.1), best)

/-- The owner of `file`, or an error naming every module in the tie. -/
def owner (file : String) : Except String ModuleId :=
  match owners file with
  | ([], _) => .error s!"{file}: no owner"
  | ([m], _) => .ok m
  | (ms, _) => .error s!"{file}: owned by {repr ms}"

end BioMech.Arch
