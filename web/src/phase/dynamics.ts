/**
 * Dynamics: parsing of `dynamics.json` (format `bm-dynamics/1`, written by
 * `pipeline/export_dynamics.py`, whose module docstring defines the fields) and the tug-of-war
 * model of one instant.
 *
 * Terms: a *moment* is how hard a muscle turns a joint coordinate, a·F·r in N·m (decision
 * D-002); a positive moment pushes the coordinate toward its `positive` joint action. At an
 * instant, the muscles pushing the way the joint moves are *agonists* and the muscles pushing
 * against that motion are *antagonists*; the *net* moment is the sum over the muscles.
 */
import { frameAt, type MusclePaths } from "../timeline/clip";
import { workType, type WorkType } from "../viewer/colour";

export const FORMAT = "bm-dynamics/1";

/** Below this joint speed (degrees per second) the joint counts as holding still. */
export const HOLD_DEG_PER_S = 5;

export interface CoordinateTrack {
  coordinate: string;
  /** Graph ids: the joint, and the joint action of each direction of the coordinate. */
  joint: string;
  positive: string;
  negative: string;
  /** Per frame, degrees. */
  angleDeg: Float64Array;
  /** Muscle graph id -> per frame, N·m. */
  moments: Map<string, Float64Array>;
}

export interface Dynamics {
  time: Float64Array;
  coordinates: CoordinateTrack[];
}

const isObject = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);

function series(x: unknown, what: string, length: number): Float64Array {
  if (!Array.isArray(x) || x.length !== length || !x.every((v) => typeof v === "number" && Number.isFinite(v))) {
    throw new Error(`dynamics.json: ${what} needs ${length} finite numbers`);
  }
  return Float64Array.from(x as number[]);
}

function str(x: unknown, what: string): string {
  if (typeof x !== "string") throw new Error(`dynamics.json: ${what} is no string`);
  return x;
}

/** Parse the decoded JSON of `dynamics.json`; throws with the offending field on a deviation from the format. */
export function parseDynamics(json: unknown): Dynamics {
  if (!isObject(json) || json["format"] !== FORMAT) throw new Error(`dynamics.json: format ${FORMAT} expected`);
  const raw = json["time"];
  if (!Array.isArray(raw) || raw.length < 2) throw new Error("dynamics.json: time needs at least two frames");
  const n = raw.length;
  const time = series(raw, "time", n);
  const cs = json["coordinates"];
  if (!Array.isArray(cs)) throw new Error("dynamics.json: coordinates missing");
  const coordinates = cs.map((c, k): CoordinateTrack => {
    if (!isObject(c) || !isObject(c["moments"])) throw new Error(`dynamics.json: coordinates[${k}] malformed`);
    const coordinate = str(c["coordinate"], `coordinates[${k}].coordinate`);
    const moments = new Map<string, Float64Array>();
    for (const [m, v] of Object.entries(c["moments"])) moments.set(m, series(v, `${coordinate}.moments.${m}`, n));
    return {
      coordinate,
      joint: str(c["joint"], `${coordinate}.joint`),
      positive: str(c["positive"], `${coordinate}.positive`),
      negative: str(c["negative"], `${coordinate}.negative`),
      angleDeg: series(c["angleDeg"], `${coordinate}.angleDeg`, n),
      moments,
    };
  });
  return { time, coordinates };
}

/** Fetch and parse `<base>dynamics.json`. */
export async function loadDynamics(base = "./"): Promise<Dynamics> {
  const res = await fetch(`${base}dynamics.json`);
  if (!res.ok) throw new Error(`dynamics.json: HTTP ${res.status}`);
  return parseDynamics(await res.json());
}

const lerp = (x: ArrayLike<number>, i0: number, i1: number, f: number) => (x[i0] ?? 0) * (1 - f) + (x[i1] ?? 0) * f;

/** One muscle's push at the instant. */
export interface Segment {
  muscle: string;
  /** N·m; the sign gives the direction (+: toward `positive`). */
  moment: number;
  activation: number;
  work: WorkType;
}

/** Where the joint is heading: toward its positive action, its negative action, or holding. */
export type Motion = "positive" | "negative" | "hold";

export interface TugOfWar {
  coordinate: string;
  joint: string;
  positive: string;
  negative: string;
  angleDeg: number;
  /** Degrees per second. */
  speedDegPerS: number;
  motion: Motion;
  net: number;
  /** Positive moments, largest first. */
  pushPositive: Segment[];
  /** Negative moments, largest magnitude first. */
  pushNegative: Segment[];
}

/** The tug of war of every coordinate at clip time `t`. Activation and lengthening velocity
 * come from the clip (`muscle_paths.json`, same frames), and give each muscle's work type. */
export function tugOfWarAt(d: Dynamics, clip: MusclePaths, t: number): TugOfWar[] {
  const { i0, i1, f } = frameAt(d.time, t);
  const a = Math.max(0, Math.min(i0, d.time.length - 2));
  const dt = (d.time[a + 1] ?? 1) - (d.time[a] ?? 0);
  return d.coordinates.map((c) => {
    const speed = ((c.angleDeg[a + 1] ?? 0) - (c.angleDeg[a] ?? 0)) / dt;
    const segs: Segment[] = [];
    for (const [muscle, m] of c.moments) {
      const track = clip.muscles.get(muscle.slice(muscle.indexOf(":") + 1));
      const activation = track ? lerp(track.activation, i0, i1, f) : 0;
      const velocity = track ? lerp(track.velocity, i0, i1, f) : 0;
      segs.push({ muscle, moment: lerp(m, i0, i1, f), activation, work: workType(activation, velocity) });
    }
    return {
      coordinate: c.coordinate,
      joint: c.joint,
      positive: c.positive,
      negative: c.negative,
      angleDeg: lerp(c.angleDeg, i0, i1, f),
      speedDegPerS: speed,
      motion: Math.abs(speed) < HOLD_DEG_PER_S ? "hold" : speed > 0 ? "positive" : "negative",
      net: segs.reduce((s, x) => s + x.moment, 0),
      pushPositive: segs.filter((x) => x.moment > 0).sort((p, q) => q.moment - p.moment),
      pushNegative: segs.filter((x) => x.moment < 0).sort((p, q) => p.moment - q.moment),
    };
  });
}

/** Per coordinate, the largest total push to one side over the stride frames (N·m): each bar's
 * fixed scale, so a bar stays put while the clip plays and fills its width at its own peak. */
export function momentScale(d: Dynamics, stride: { start: number; end: number }): Map<string, number> {
  const out = new Map<string, number>();
  for (const c of d.coordinates) {
    let max = 1;
    d.time.forEach((t, i) => {
      if (t < stride.start || t > stride.end) return;
      let pos = 0;
      let neg = 0;
      for (const m of c.moments.values()) {
        const v = m[i] ?? 0;
        if (v > 0) pos += v;
        else neg -= v;
      }
      max = Math.max(max, pos, neg);
    });
    out.set(c.coordinate, max);
  }
  return out;
}
