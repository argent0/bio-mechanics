/**
 * Muscle colour scale (the single definition; the legend is generated from these constants).
 *
 * Inputs per muscle and frame: activation `a` in 0-1 and lengthening velocity `v` in m/s of the
 * muscle-tendon unit (`v > 0` lengthening).
 *
 * Work type (hue):
 *  - eccentric  : lengthening while active, `v > V_ISOMETRIC` and `a >= A_ACTIVE`; the muscle brakes; orange
 *  - concentric : shortening while active, `v < -V_ISOMETRIC` and `a >= A_ACTIVE`; the muscle drives; blue
 *  - isometric  : `|v| <= V_ISOMETRIC`, or an inactive muscle (`a < A_ACTIVE`); it holds length or rests; grey-violet
 * Activation (brightness and opacity), linear in `a`:
 *  - lightness `L_MIN + (L_MAX - L_MIN) a`   (dark scene: brighter means more active)
 *  - opacity   `OPACITY_MIN + (1 - OPACITY_MIN) a`
 */

export type WorkType = "eccentric" | "concentric" | "isometric";

/** Below this speed (m/s) a muscle counts as holding its length. */
export const V_ISOMETRIC = 0.02;
/** Below this activation a muscle counts as inactive: it does no active work. */
export const A_ACTIVE = 0.05;

export const HUE: Readonly<Record<WorkType, number>> = { eccentric: 24, concentric: 208, isometric: 268 };
export const SATURATION: Readonly<Record<WorkType, number>> = { eccentric: 0.9, concentric: 0.8, isometric: 0.22 };
export const L_MIN = 0.3;
export const L_MAX = 0.72;
export const OPACITY_MIN = 0.2;

export const WORK_LABEL: Readonly<Record<WorkType, string>> = {
  eccentric: "braking (lengthening while active)",
  concentric: "driving (shortening while active)",
  isometric: "holding (steady length) or resting",
};

export function workType(activation: number, velocity: number): WorkType {
  if (activation < A_ACTIVE || Math.abs(velocity) <= V_ISOMETRIC) return "isometric";
  return velocity > 0 ? "eccentric" : "concentric";
}

export interface MuscleColour {
  work: WorkType;
  /** Hue in degrees. */
  h: number;
  s: number;
  l: number;
  opacity: number;
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

export function muscleColour(activation: number, velocity: number): MuscleColour {
  const a = clamp01(activation);
  const work = workType(a, velocity);
  return {
    work,
    h: HUE[work],
    s: SATURATION[work],
    l: L_MIN + (L_MAX - L_MIN) * a,
    opacity: OPACITY_MIN + (1 - OPACITY_MIN) * a,
  };
}

/** HSL (h in degrees, s and l in 0-1) to sRGB components in 0-1. */
export function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  const [r, g, b] = hp < 1 ? [c, x, 0] : hp < 2 ? [x, c, 0] : hp < 3 ? [0, c, x] : hp < 4 ? [0, x, c] : hp < 5 ? [x, 0, c] : [c, 0, x];
  const m = l - c / 2;
  return [r + m, g + m, b + m];
}

/** CSS `hsl()` string of a colour, for the legend. */
export function cssColour(c: MuscleColour): string {
  return `hsl(${c.h} ${(c.s * 100).toFixed(0)}% ${(c.l * 100).toFixed(0)}% / ${c.opacity.toFixed(2)})`;
}
