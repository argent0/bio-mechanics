/**
 * Camera framing: the camera distance at which the bounds of the whole skeleton fit the view.
 * Pure arithmetic on boxes, so it is tested without a GPU.
 *
 * Terms: the *bounds* are the axis-aligned box around every mesh of the mesh index (both legs,
 * pelvis, torso, arms, head, hands); the *frame* is the sphere around those bounds.
 */

export type Vec3 = readonly [number, number, number];

export interface Bounds {
  min: Vec3;
  max: Vec3;
}

/** The smallest box around every box in `boxes`; `undefined` for an empty list. */
export function unionBounds(boxes: readonly Bounds[]): Bounds | undefined {
  const finite = boxes.filter((b) => [...b.min, ...b.max].every(Number.isFinite));
  if (finite.length === 0) return undefined;
  const lo = (i: 0 | 1 | 2) => Math.min(...finite.map((b) => b.min[i]));
  const hi = (i: 0 | 1 | 2) => Math.max(...finite.map((b) => b.max[i]));
  return { min: [lo(0), lo(1), lo(2)], max: [hi(0), hi(1), hi(2)] };
}

export interface CameraFit {
  centre: Vec3;
  /** Radius of the sphere around the bounds, metres. */
  radius: number;
  /** Camera distance from `centre` at which the sphere, plus `margin`, fills the narrower view axis. */
  distance: number;
}

/** Where to put the camera so `bounds` fit a view of vertical field of view `vfovDeg` and width
 * over height `aspect`; `margin` is the room kept around the body (1.1: ten percent). The sphere
 * keeps the body in view from every orbit angle. */
export function fitCamera(bounds: Bounds, vfovDeg: number, aspect: number, margin = 1.1): CameraFit {
  const centre: Vec3 = [0, 1, 2].map((i) => (bounds.min[i]! + bounds.max[i]!) / 2) as unknown as Vec3;
  const radius = Math.hypot(...([0, 1, 2].map((i) => (bounds.max[i]! - bounds.min[i]!) / 2) as [number, number, number]));
  const v = (vfovDeg * Math.PI) / 180 / 2;
  const h = Math.atan(Math.tan(v) * Math.max(aspect, 1e-3));
  const half = Math.min(v, h);
  return { centre, radius, distance: (radius * margin) / Math.sin(half) };
}
