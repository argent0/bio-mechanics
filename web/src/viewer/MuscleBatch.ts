/**
 * MuscleBatch: the tubes of one region and side in one geometry and one draw call.
 *
 * Each tube owns a fixed slice of the vertex buffers (`VERTS` vertices). Colour and opacity live
 * per vertex (RGBA), so every tube keeps its own look inside the shared material. The index
 * buffer lists the visible tubes first; `setVisible` rewrites it and narrows the draw range, so
 * hidden tubes cost nothing per frame. A face index maps back to its tube (`tubeAtFace`).
 */
import * as THREE from "three";
import { hslToRgb, muscleColour } from "./colour";
import { RADIAL, RINGS, lerp, tubeIndices, writeTube } from "./tube";

export const VERTS = RINGS * RADIAL;
const INDICES_PER_TUBE = (RINGS - 1) * RADIAL * 6;
const TRIS_PER_TUBE = INDICES_PER_TUBE / 3;
const TEMPLATE = tubeIndices();

export interface BatchTube {
  name: string;
  nodeId: string;
  /** Per frame, the path resampled to `RINGS` points. */
  frames: Float32Array[];
  activation: Float32Array;
  velocity: Float32Array;
}

export interface TubeLook {
  radius: number;
  /** Multiplies the opacity of the activation ramp (1 = as is). */
  opacityFactor: number;
  /** Opacity 1 (the selected muscle). */
  solid: boolean;
}

export class MuscleBatch {
  readonly mesh: THREE.Mesh;
  private readonly positions: Float32Array;
  private readonly normals: Float32Array;
  private readonly colours: Float32Array;
  private readonly index: THREE.BufferAttribute;
  private readonly geometry = new THREE.BufferGeometry();
  private shown: number[] = [];

  constructor(readonly key: string, readonly tubes: readonly BatchTube[], material: THREE.Material) {
    const n = tubes.length * VERTS;
    this.positions = new Float32Array(n * 3);
    this.normals = new Float32Array(n * 3);
    this.colours = new Float32Array(n * 4);
    this.index = new THREE.BufferAttribute(new Uint32Array(tubes.length * INDICES_PER_TUBE), 1);
    this.geometry.setAttribute("position", new THREE.BufferAttribute(this.positions, 3).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setAttribute("normal", new THREE.BufferAttribute(this.normals, 3).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setAttribute("color", new THREE.BufferAttribute(this.colours, 4).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setIndex(this.index);
    // Tubes move through the scene, so a fixed generous sphere stands in for the bounds.
    this.geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e3);
    this.mesh = new THREE.Mesh(this.geometry, material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 1;
    this.setVisible(() => true);
  }

  get visibleCount(): number {
    return this.shown.length;
  }

  /** Show the tubes for which `keep` holds. */
  setVisible(keep: (t: BatchTube) => boolean): void {
    this.shown = [];
    this.tubes.forEach((t, i) => {
      if (keep(t)) this.shown.push(i);
    });
    const out = this.index.array as Uint32Array;
    this.shown.forEach((tubeIndex, slot) => {
      const base = tubeIndex * VERTS;
      for (let k = 0; k < INDICES_PER_TUBE; k++) out[slot * INDICES_PER_TUBE + k] = (TEMPLATE[k] as number) + base;
    });
    this.index.needsUpdate = true;
    this.geometry.setDrawRange(0, this.shown.length * INDICES_PER_TUBE);
    this.mesh.visible = this.shown.length > 0;
  }

  /** The visible tube a face of the draw hit, if any. */
  tubeAtFace(faceIndex: number | null | undefined): BatchTube | undefined {
    if (faceIndex == null) return undefined;
    const tubeIndex = this.shown[Math.floor(faceIndex / TRIS_PER_TUBE)];
    return tubeIndex === undefined ? undefined : this.tubes[tubeIndex];
  }

  /** Rewrite the visible tubes for the clip time between frames `i0` and `i1` (fraction `f`). */
  update(i0: number, i1: number, f: number, look: (t: BatchTube) => TubeLook, scratch: Float32Array): void {
    for (const ti of this.shown) {
      const t = this.tubes[ti] as BatchTube;
      const a = t.frames[i0];
      const b = t.frames[i1];
      if (!a || !b) continue;
      for (let k = 0; k < scratch.length; k++) scratch[k] = lerp(a[k], b[k], f);
      const l = look(t);
      const v0 = ti * VERTS;
      writeTube(scratch, l.radius, this.positions.subarray(v0 * 3, (v0 + VERTS) * 3), this.normals.subarray(v0 * 3, (v0 + VERTS) * 3));
      const c = muscleColour(lerp(t.activation[i0], t.activation[i1], f), lerp(t.velocity[i0], t.velocity[i1], f));
      const [r, g, bl] = hslToRgb(c.h, c.s, c.l);
      const alpha = l.solid ? 1 : c.opacity * l.opacityFactor;
      for (let v = 0; v < VERTS; v++) {
        const o = (v0 + v) * 4;
        this.colours[o] = r;
        this.colours[o + 1] = g;
        this.colours[o + 2] = bl;
        this.colours[o + 3] = alpha;
      }
    }
    for (const name of ["position", "normal", "color"]) (this.geometry.getAttribute(name) as THREE.BufferAttribute).needsUpdate = true;
  }

  dispose(): void {
    this.geometry.dispose();
  }
}
