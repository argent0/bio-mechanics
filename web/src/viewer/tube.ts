/**
 * Tube geometry along a muscle path, written into preallocated buffers.
 *
 * A path of any point count is resampled to `RINGS` points evenly spaced by arc length
 * (`resamplePath`); `writeTube` places `RADIAL` vertices on a circle around each resampled point,
 * in a frame carried along the path (parallel transport, so the tube does not twist). The
 * radius follows a spindle: `SPINDLE_MIN` of the nominal radius at the ends, 1 in the middle.
 */

export const RINGS = 20;
export const RADIAL = 8;
export const SPINDLE_MIN = 0.55;

/** Triangle indices of a tube (static; shared by every tube). */
export function tubeIndices(): Uint16Array {
  const idx = new Uint16Array((RINGS - 1) * RADIAL * 6);
  let k = 0;
  for (let i = 0; i < RINGS - 1; i++) {
    for (let j = 0; j < RADIAL; j++) {
      const a = i * RADIAL + j;
      const b = i * RADIAL + ((j + 1) % RADIAL);
      const c = (i + 1) * RADIAL + j;
      const d = (i + 1) * RADIAL + ((j + 1) % RADIAL);
      idx.set([a, c, b, b, c, d], k);
      k += 6;
    }
  }
  return idx;
}

/** Resample the flat xyz polyline `points` (at least two points) to `RINGS` points evenly spaced by arc length, into `out` (`RINGS * 3`). */
export function resamplePath(points: ArrayLike<number>, out: Float32Array): Float32Array {
  const n = Math.floor(points.length / 3);
  const cum = new Float64Array(n);
  for (let i = 1; i < n; i++) {
    const dx = (points[i * 3] ?? 0) - (points[(i - 1) * 3] ?? 0);
    const dy = (points[i * 3 + 1] ?? 0) - (points[(i - 1) * 3 + 1] ?? 0);
    const dz = (points[i * 3 + 2] ?? 0) - (points[(i - 1) * 3 + 2] ?? 0);
    cum[i] = (cum[i - 1] ?? 0) + Math.hypot(dx, dy, dz);
  }
  const total = cum[n - 1] ?? 0;
  let seg = 1;
  for (let r = 0; r < RINGS; r++) {
    const s = (total * r) / (RINGS - 1);
    while (seg < n - 1 && (cum[seg] ?? 0) < s) seg++;
    const c0 = cum[seg - 1] ?? 0;
    const c1 = cum[seg] ?? c0;
    const w = c1 > c0 ? Math.min(1, Math.max(0, (s - c0) / (c1 - c0))) : 0;
    for (let k = 0; k < 3; k++) {
      const p0 = points[(seg - 1) * 3 + k] ?? 0;
      const p1 = points[seg * 3 + k] ?? p0;
      out[r * 3 + k] = p0 + (p1 - p0) * w;
    }
  }
  return out;
}

/**
 * Write the tube's vertex positions and normals (`RINGS * RADIAL * 3` each) around the
 * centreline `centre` (`RINGS * 3`, from `resamplePath`) with nominal radius `radius` (m).
 */
export function writeTube(centre: Float32Array, radius: number, positions: Float32Array, normals: Float32Array): void {
  let nx = 0;
  let ny = 0;
  let nz = 0;
  for (let i = 0; i < RINGS; i++) {
    const a = Math.max(0, i - 1) * 3;
    const b = Math.min(RINGS - 1, i + 1) * 3;
    let tx = (centre[b] ?? 0) - (centre[a] ?? 0);
    let ty = (centre[b + 1] ?? 0) - (centre[a + 1] ?? 0);
    let tz = (centre[b + 2] ?? 0) - (centre[a + 2] ?? 0);
    const tl = Math.hypot(tx, ty, tz) || 1;
    tx /= tl;
    ty /= tl;
    tz /= tl;
    if (i === 0) {
      // Reference axis: the world axis least aligned with the tangent.
      const ax = Math.abs(tx) < Math.abs(ty) && Math.abs(tx) < Math.abs(tz) ? 1 : 0;
      const ay = !ax && Math.abs(ty) < Math.abs(tz) ? 1 : 0;
      const az = !ax && !ay ? 1 : 0;
      nx = ax;
      ny = ay;
      nz = az;
    }
    // Remove the tangent component from the carried normal, renormalise.
    const dot = nx * tx + ny * ty + nz * tz;
    nx -= dot * tx;
    ny -= dot * ty;
    nz -= dot * tz;
    const nl = Math.hypot(nx, ny, nz) || 1;
    nx /= nl;
    ny /= nl;
    nz /= nl;
    const bx = ty * nz - tz * ny;
    const by = tz * nx - tx * nz;
    const bz = tx * ny - ty * nx;
    const r = radius * (SPINDLE_MIN + (1 - SPINDLE_MIN) * Math.sin((Math.PI * i) / (RINGS - 1)));
    const px = centre[i * 3] ?? 0;
    const py = centre[i * 3 + 1] ?? 0;
    const pz = centre[i * 3 + 2] ?? 0;
    for (let j = 0; j < RADIAL; j++) {
      const th = (2 * Math.PI * j) / RADIAL;
      const c = Math.cos(th);
      const s = Math.sin(th);
      const ox = c * nx + s * bx;
      const oy = c * ny + s * by;
      const oz = c * nz + s * bz;
      const o = (i * RADIAL + j) * 3;
      positions[o] = px + r * ox;
      positions[o + 1] = py + r * oy;
      positions[o + 2] = pz + r * oz;
      normals[o] = ox;
      normals[o + 1] = oy;
      normals[o + 2] = oz;
    }
  }
}
