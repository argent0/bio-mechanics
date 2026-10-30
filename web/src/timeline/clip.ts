/**
 * The movement clip: parsing of `muscle_paths.json` (format `bm-muscle-paths/1`, written by
 * `pipeline/export_muscle_paths.py`, whose module docstring defines the fields) and the
 * lookup of the stride inside the clip.
 *
 * Terms: a *frame* is one sample of the clip at `rateHz`; a *stride* is one complete gait
 * cycle of the right leg, from one initial contact of the right foot to the next; the graph's
 * `hasPhase` percentages (`startPct`, `endPct`) are percent of the stride.
 */

export const FORMAT = "bm-muscle-paths/1";

/** Per muscle, per frame: the path points, the activation (0-1), and the lengthening velocity (m/s, > 0 lengthening). */
export interface MuscleTrack {
  /** Per frame, flat `[x0, y0, z0, x1, ...]` in metres, origin to insertion; the count varies by frame. */
  points: Float32Array[];
  activation: Float32Array;
  velocity: Float32Array;
}

/** The stride inside the clip, in seconds. */
export interface Stride {
  start: number;
  end: number;
}

export interface MusclePaths {
  rateHz: number;
  /** Seconds per frame. */
  time: Float64Array;
  /** Per body, `7 * frames` numbers: per frame `[px, py, pz, qx, qy, qz, qw]` (m, unit quaternion). */
  bodies: Map<string, Float32Array>;
  muscles: Map<string, MuscleTrack>;
  /** Present when the file carries it (`stride: {start, end}`); `findStride` estimates it otherwise. */
  stride?: Stride;
}

const isObject = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);

function num(x: unknown, what: string): number {
  if (typeof x !== "number" || !Number.isFinite(x)) throw new Error(`muscle_paths.json: ${what} is no finite number`);
  return x;
}

function numberArray(x: unknown, what: string, length: number): Float64Array {
  if (!Array.isArray(x) || x.length !== length) throw new Error(`muscle_paths.json: ${what} needs ${length} entries`);
  return Float64Array.from(x.map((v, i) => num(v, `${what}[${i}]`)));
}

/** Parse the decoded JSON of `muscle_paths.json`; throws with the offending field on a deviation from the format. */
export function parseMusclePaths(json: unknown): MusclePaths {
  if (!isObject(json) || json["format"] !== FORMAT) throw new Error(`muscle_paths.json: format ${FORMAT} expected`);
  const rateHz = num(json["rateHz"], "rateHz");
  const timeRaw = json["time"];
  if (!Array.isArray(timeRaw) || timeRaw.length < 2) throw new Error("muscle_paths.json: time needs at least two frames");
  const frames = timeRaw.length;
  const time = numberArray(timeRaw, "time", frames);

  const bodies = new Map<string, Float32Array>();
  const bodiesRaw = json["bodies"];
  if (!isObject(bodiesRaw)) throw new Error("muscle_paths.json: bodies missing");
  for (const [name, poses] of Object.entries(bodiesRaw)) {
    if (!Array.isArray(poses) || poses.length !== frames) throw new Error(`muscle_paths.json: bodies.${name} needs ${frames} frames`);
    const flat = new Float32Array(frames * 7);
    poses.forEach((pose, f) => {
      if (!Array.isArray(pose) || pose.length !== 7) throw new Error(`muscle_paths.json: bodies.${name}[${f}] needs 7 numbers`);
      pose.forEach((v, k) => (flat[f * 7 + k] = num(v, `bodies.${name}[${f}][${k}]`)));
    });
    bodies.set(name, flat);
  }

  const muscles = new Map<string, MuscleTrack>();
  const musclesRaw = json["muscles"];
  if (!isObject(musclesRaw)) throw new Error("muscle_paths.json: muscles missing");
  for (const [name, m] of Object.entries(musclesRaw)) {
    if (!isObject(m)) throw new Error(`muscle_paths.json: muscles.${name} is no object`);
    const pts = m["points"];
    if (!Array.isArray(pts) || pts.length !== frames) throw new Error(`muscle_paths.json: muscles.${name}.points needs ${frames} frames`);
    const points = pts.map((p, f) => {
      if (!Array.isArray(p) || p.length % 3 !== 0 || p.length < 6) throw new Error(`muscle_paths.json: muscles.${name}.points[${f}] needs at least two xyz points`);
      return Float32Array.from(p.map((v, k) => num(v, `muscles.${name}.points[${f}][${k}]`)));
    });
    muscles.set(name, {
      points,
      activation: Float32Array.from(numberArray(m["activation"], `muscles.${name}.activation`, frames)),
      velocity: Float32Array.from(numberArray(m["velocity"], `muscles.${name}.velocity`, frames)),
    });
  }

  const out: MusclePaths = { rateHz, time, bodies, muscles };
  const s = json["stride"];
  if (isObject(s)) out.stride = { start: num(s["start"], "stride.start"), end: num(s["end"], "stride.end") };
  return out;
}

/** Fetch and parse `<base>muscle_paths.json`. */
export async function loadMusclePaths(base = "./"): Promise<MusclePaths> {
  const res = await fetch(`${base}muscle_paths.json`);
  if (!res.ok) throw new Error(`muscle_paths.json: HTTP ${res.status}`);
  return parseMusclePaths(await res.json());
}

/**
 * The stride inside the clip: the file's own `stride` when present; otherwise estimated
 * kinematically as the pipeline's detector does (`pipeline/segment_phases.py`, Zeni et al.
 * 2008): initial contacts of the right foot are the maxima of the right heel's position ahead
 * of the pelvis along +x. Here the right calcaneus frame stands in for the heel marker, and each
 * maximum is refined by a parabola through its three frames. The stride runs from the first
 * maximum to the next; with fewer than two maxima it spans the whole clip.
 */
export function findStride(clip: MusclePaths): Stride {
  if (clip.stride) return clip.stride;
  const first = clip.time[0] ?? 0;
  const last = clip.time[clip.time.length - 1] ?? first;
  const heel = clip.bodies.get("calcn_r");
  const pelvis = clip.bodies.get("pelvis");
  if (!heel || !pelvis) return { start: first, end: last };
  const n = clip.time.length;
  const ahead = (f: number) => (heel[f * 7] ?? 0) - (pelvis[f * 7] ?? 0);
  const contacts: number[] = [];
  for (let f = 1; f < n - 1; f++) {
    const a = ahead(f - 1);
    const b = ahead(f);
    const c = ahead(f + 1);
    if (b >= a && b > c) {
      const denom = a - 2 * b + c;
      const shift = denom === 0 ? 0 : (0.5 * (a - c)) / denom;
      const t = clip.time[f] ?? 0;
      const dt = (clip.time[f + (shift >= 0 ? 1 : -1)] ?? t) - t;
      contacts.push(t + Math.abs(shift) * dt);
    }
  }
  const [start, end] = contacts;
  return start !== undefined && end !== undefined ? { start, end } : { start: first, end: last };
}

/** The two frames around time `t` and the weight of the second (0-1); `t` outside the clip clamps to its ends. */
export function frameAt(time: ArrayLike<number>, t: number): { i0: number; i1: number; f: number } {
  const n = time.length;
  if (t <= (time[0] ?? 0)) return { i0: 0, i1: 0, f: 0 };
  if (t >= (time[n - 1] ?? 0)) return { i0: n - 1, i1: n - 1, f: 0 };
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if ((time[mid] ?? 0) <= t) lo = mid;
    else hi = mid;
  }
  const a = time[lo] ?? 0;
  const b = time[hi] ?? a;
  return { i0: lo, i1: hi, f: b > a ? (t - a) / (b - a) : 0 };
}
