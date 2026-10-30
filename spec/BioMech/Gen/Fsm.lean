import BioMech.Gen.Model

/-!
# DFA emitters: `generated/ts/gaitFsm.ts`, `generated/ts/uiFsm.ts`, `generated/py/gait_fsm.py`

Each file holds, for one DFA (`FsmSpec`):

* the state and event types (`GaitPhase`, `GaitEvent`, … as string unions or
  `Literal`s), with each constructor's docstring as a comment;
* `STATES` and `EVENTS` (the Lean `all` lists), further state lists such as
  `PHASES`, `START`, `ACCEPT`;
* `TRANSITIONS`, the explicit rows of the Lean `transitions` list;
* `TABLE`, the complete table: `step s e` evaluated in Lean for every pair, so
  the implicit steps (the gait sink `invalid`, the UI self-loops) are explicit
  data here;
* `step(state, event)` (a table lookup), `run(word, start)`, `accepts(word)`;
* the words, such as `STRIDE_WORD` and `RESET_WORD`.
-/

namespace BioMech.Gen

def FsmSpec.source (f : FsmSpec) : String := f.loc.file

/-- A sentence on the steps of pairs absent from `TRANSITIONS`. -/
def Implicit.describe : Implicit → String
  | .sink s => s!"Every (state, event) pair absent from `TRANSITIONS` goes to `{s}`."
  | .selfLoop => "Every (state, event) pair absent from `TRANSITIONS` leaves the state as it is."
  | .mixed => "Pairs absent from `TRANSITIONS` take the targets listed in `TABLE`."

def Implicit.label : Implicit → String
  | .sink _ => "sink"
  | .selfLoop => "selfLoop"
  | .mixed => "mixed"

/-! ## TypeScript -/

def tsStrs (xs : List String) : String := "[" ++ ", ".intercalate (xs.map jsonQuote) ++ "]"

def tsUnion (name : String) (doc : Option String) (items : List Item) : List String :=
  tsComment "" doc ++ [s!"export type {name} ="] ++
  items.flatMap (fun i => tsComment "  " i.doc ++ [s!"  | {jsonQuote i.name}"]) ++ ["  ;", ""]

def tsFsm (f : FsmSpec) : String :=
  let S := f.config.state
  let E := f.config.event
  let c := f.config
  let list (n : String) (ty : String) (doc : Option String) (xs : List String) :=
    tsComment "" doc ++ [s!"export const {n}: readonly {ty}[] = {tsStrs xs};", ""]
  let row (r : String × String × String) :=
    s!"  \{ from: {jsonQuote r.1}, event: {jsonQuote r.2.1}, to: {jsonQuote r.2.2} },"
  let tableRow (r : String × List String) :=
    let cells := (f.events.zip r.2).map fun (e, t) => s!"{e.name}: {jsonQuote t}"
    s!"  {r.1}: \{ {", ".intercalate cells} },"
  let lines :=
    [s!"// {headerText f.source}", ""] ++
    tsUnion S f.stateDoc f.states ++
    tsUnion E f.eventDoc f.events ++
    list "STATES" S (some s!"Every state, in the order of `{c.states}`.") (f.states.map (·.name)) ++
    list "EVENTS" E (some s!"Every event, in the order of `{c.events}`.") (f.events.map (·.name)) ++
    f.stateLists.flatMap (fun l => list (upperSnake l.lean) S l.doc l.values) ++
    [s!"/** The start state (`{c.start}`). */",
     s!"export const START: {S} = {jsonQuote f.start};", ""] ++
    list "ACCEPT" S f.acceptDoc f.accept ++
    ["/** One explicit row of the transition table. */",
     "export interface Transition {", s!"  readonly from: {S};", s!"  readonly event: {E};",
     s!"  readonly to: {S};", "}", ""] ++
    tsComment "" f.rowsDoc ++
    ["export const TRANSITIONS: readonly Transition[] = ["] ++ f.rows.map row ++ ["];", ""] ++
    tsComment "" (some s!"The complete transition table: `{c.step} s e` evaluated in Lean for every state `s` and event `e`. {f.implicit.describe}") ++
    [s!"export const TABLE: \{ readonly [S in {S}]: \{ readonly [E in {E}]: {S} } } = \{"] ++
    f.table.map tableRow ++ ["};", ""] ++
    tsComment "" f.stepDoc ++
    [s!"export function step(state: {S}, event: {E}): {S} \{", "  return TABLE[state][event];", "}", "",
     "/** The state after reading `word` from `start`, one `step` per event. */",
     s!"export function run(word: readonly {E}[], start: {S} = START): {S} \{",
     "  return word.reduce((state, event) => step(state, event), start);", "}", "",
     "/** `word`, read from `START`, ends in an accept state. */",
     s!"export function accepts(word: readonly {E}[]): boolean \{",
     "  return ACCEPT.includes(run(word));", "}"] ++
    f.words.flatMap (fun w => [""] ++ tsComment "" w.doc ++
      [s!"export const {upperSnake w.lean}: readonly {E}[] = {tsStrs w.values};"])
  "\n".intercalate lines ++ "\n"

/-! ## Python -/

def pyTuple (xs : List String) : String :=
  match xs with
  | [x] => s!"({jsonQuote x},)"
  | _ => "(" ++ ", ".intercalate (xs.map jsonQuote) ++ ")"

def pyLiteral (name : String) (doc : Option String) (items : List Item) : List String :=
  [s!"{name} = Literal["] ++
  items.flatMap (fun i => hashComment "    " i.doc ++ [s!"    {jsonQuote i.name},"]) ++ ["]"] ++
  pyDocstring "" doc ++ [""]

def pyFsm (f : FsmSpec) : String :=
  let S := f.config.state
  let E := f.config.event
  let c := f.config
  let tuple (n ty : String) (doc : Option String) (xs : List String) :=
    [s!"{n}: Final[tuple[{ty}, ...]] = {pyTuple xs}"] ++ pyDocstring "" doc ++ [""]
  let row (r : String × String × String) :=
    s!"    ({jsonQuote r.1}, {jsonQuote r.2.1}, {jsonQuote r.2.2}),"
  let tableRow (r : String × List String) :=
    let cells := (f.events.zip r.2).map fun (e, t) => s!"{jsonQuote e.name}: {jsonQuote t}"
    s!"    {jsonQuote r.1}: \{{", ".intercalate cells}},"
  let lines :=
    [s!"# {headerText f.source}",
     s!"\"\"\"Tables of the DFA in `{f.source}`: states, events, transitions, and `step`.\"\"\"",
     "", "from __future__ import annotations", "",
     "from collections.abc import Iterable",
     "from typing import Final, Literal", ""] ++
    pyLiteral S f.stateDoc f.states ++
    pyLiteral E f.eventDoc f.events ++
    tuple "STATES" S (some s!"Every state, in the order of `{c.states}`.") (f.states.map (·.name)) ++
    tuple "EVENTS" E (some s!"Every event, in the order of `{c.events}`.") (f.events.map (·.name)) ++
    f.stateLists.flatMap (fun l => tuple (upperSnake l.lean) S l.doc l.values) ++
    [s!"START: Final[{S}] = {jsonQuote f.start}", s!"\"\"\"The start state (`{c.start}`).\"\"\"", ""] ++
    tuple "ACCEPT" S f.acceptDoc f.accept ++
    [s!"TRANSITIONS: Final[tuple[tuple[{S}, {E}, {S}], ...]] = ("] ++ f.rows.map row ++ [")"] ++
    pyDocstring "" f.rowsDoc ++ [""] ++
    [s!"TABLE: Final[dict[{S}, dict[{E}, {S}]]] = \{"] ++ f.table.map tableRow ++ ["}"] ++
    pyDocstring "" (some s!"The complete transition table: `{c.step} s e` evaluated in Lean for every state `s` and event `e`. {f.implicit.describe}") ++
    ["", "",
     s!"def step(state: {S}, event: {E}) -> {S}:"] ++ pyDocstring "    " f.stepDoc ++
    ["    return TABLE[state][event]", "", "",
     s!"def run(word: Iterable[{E}], start: {S} = START) -> {S}:",
     "    \"\"\"The state after reading `word` from `start`, one `step` per event.\"\"\"",
     "    state = start", "    for event in word:", "        state = step(state, event)",
     "    return state", "", "",
     s!"def accepts(word: Iterable[{E}]) -> bool:",
     "    \"\"\"`word`, read from `START`, ends in an accept state.\"\"\"",
     "    return run(word) in ACCEPT", ""] ++
    f.words.flatMap (fun w => [""] ++ tuple (upperSnake w.lean) E w.doc w.values)
  "\n".intercalate (dropTrailingBlank lines) ++ "\n"

end BioMech.Gen
