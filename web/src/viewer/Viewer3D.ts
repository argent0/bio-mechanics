/**
 * Viewer3D: the Three.js scene of the movement.
 *
 * Scene: bones from `meshes/index.json` (glTF per body, body frame, y up) posed per frame from
 * `muscle_paths.json` `bodies`; muscles as tubes along their path points (decision D8), the
 * walker moving along +x. Between two clip frames, poses and paths interpolate linearly
 * (rotations by slerp), so playback at any speed stays smooth.
 *
 * Muscle appearance: see `colour.ts` (hue by work type, lightness and opacity by activation).
 * The legend in the corner is generated from the same constants.
 *
 * Framing: on mount the camera fits the bounds of every mesh in the mesh index (`frame.ts`), so
 * the whole skeleton shows, legs to head and hands; the fit follows resizes until the first drag.
 * An optional `RegionFilter` hides the muscle tubes outside the chosen regions and sides.
 *
 * Interaction: orbit camera (drag, wheel); the camera follows the pelvis along x. Hover names a
 * muscle; a click on a muscle with a graph node selects `muscle:<opensim name>` through the
 * Timeline (`selectNode`); a click on empty space clears the selection.
 *
 * Bones hide with the region filter: a body shows while any bone node on it (matched by
 * `opensimName`) passes the selection (`region/bones.ts`).
 *
 * Performance: the tubes of one region and side share one geometry and one draw call
 * (`MuscleBatch.ts`, grouping in `batch.ts`), buffers preallocated and rewritten in place per
 * frame; one shared material for all bones; the scene draws on demand (when the playhead, the
 * selection, or the camera changes). In dev mode a readout in the corner and a console line
 * per second give the frame rate and the draw calls (`fpsLine`).
 */
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { QueryEngine } from "../query/QueryEngine";
import { frameAt, type MusclePaths } from "../timeline/clip";
import type { Timeline } from "../timeline/Timeline";
import { A_ACTIVE, L_MAX, L_MIN, OPACITY_MIN, V_ISOMETRIC, WORK_LABEL, hslToRgb, muscleColour, cssColour, type WorkType } from "./colour";
import { bodyPasses, bodyPlacements, type Placed, type RegionFilter } from "../region";
import { fitCamera, unionBounds } from "./frame";
import { parseMeshIndex } from "./meshIndex";
import { planBatches } from "./batch";
import { MuscleBatch, type BatchTube, type TubeLook } from "./MuscleBatch";
import { RINGS, lerp, resamplePath } from "./tube";

/** Nominal tube radius: a muscle belly is wider than the model's path points suggest; this reads well at body scale. */
export const TUBE_RADIUS_M = 0.011;
const SELECTED_RADIUS_FACTOR = 1.7;
/** Room around the skeleton in the fitted view (1.12: twelve percent). */
const FIT_MARGIN = 1.12;
/** From the centre of the skeleton toward the camera: the walker's side, a little above and ahead. */
const VIEW_DIRECTION = new THREE.Vector3(0.25, 0.18, 1).normalize();
const DIMMED_OPACITY_FACTOR = 0.35;

export interface Viewer3DOptions {
  query: QueryEngine;
  timeline: Timeline;
  /** URL prefix of the pipeline output (`graph.json`, `meshes/`, `muscle_paths.json`), default `./`. */
  dataBase?: string;
  /** Hides the muscles outside its region and side selection. */
  filter?: RegionFilter;
}

/** The dev readout line: frame rate and draw calls of the last second. */
export function fpsLine(fps: number, calls: number, batches: number, muscles: number): string {
  return `${fps.toFixed(1)} fps, ${calls} draw calls (${batches} muscle batches, ${muscles} muscles shown)`;
}

const DEV = (import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV === true;

export class Viewer3D {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(40, 1, 0.05, 50);
  private readonly controls: OrbitControls;
  private readonly bodyNodes = new Map<string, THREE.Object3D>();
  private readonly batches: MuscleBatch[] = [];
  private readonly bodyPlaces = new Map<string, Placed[]>();
  private readonly tubeMaterial = new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0, vertexColors: true, transparent: true, side: THREE.DoubleSide, depthWrite: false });
  private fpsEl: HTMLDivElement | null = null;
  private pendingHover: PointerEvent | null = null;
  private readonly raycaster = new THREE.Raycaster();
  private readonly tooltip: HTMLDivElement;
  private readonly offs: (() => void)[] = [];
  private readonly scratchA = new THREE.Quaternion();
  private readonly scratchB = new THREE.Quaternion();
  private readonly scratch = new Float32Array(RINGS * 3);
  private readonly ground = new THREE.GridHelper(12, 24, 0x6b7a90, 0x3a4658);
  private lastPelvisX: number | null = 0;
  private dirty = true;
  private raf = 0;
  private selectedName: string | null = null;
  /** True once the user has moved the camera; the fit then stops following resizes. */
  private userMoved = false;
  private frameCount = 0;
  private fpsWindowStart = performance.now();
  /** Frames drawn per second, measured over the last second of drawing. */
  fps = 0;
  /** Draw calls of the last frame (muscle batches plus bone meshes). */
  drawCalls = 0;

  private constructor(private readonly el: HTMLElement, private readonly opts: Viewer3DOptions) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.scene.background = new THREE.Color(0x14181f);
    el.style.position = el.style.position || "relative";
    el.append(this.renderer.domElement);
    this.renderer.domElement.style.cssText = "display:block;width:100%;height:100%;";
    this.tooltip = Object.assign(document.createElement("div"), { className: "bm-v-tip" });
    this.tooltip.style.cssText = "position:absolute;pointer-events:none;padding:2px 6px;border-radius:3px;background:rgba(0,0,0,.75);color:#fff;font:12px system-ui;display:none;";
    el.append(this.tooltip, this.buildLegend());
    if (DEV) {
      this.fpsEl = Object.assign(document.createElement("div"), { className: "bm-v-fps", textContent: "fps: move the playhead" });
      this.fpsEl.style.cssText = "position:absolute;right:10px;top:10px;padding:3px 8px;border-radius:4px;background:rgba(10,12,16,.72);color:#9fe3a8;font:12px ui-monospace,monospace;pointer-events:none;";
      el.append(this.fpsEl);
      (window as unknown as { __bmViewer?: Viewer3D }).__bmViewer = this;
    }

    this.scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x303845, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.8);
    sun.position.set(2, 4, 3);
    this.scene.add(sun);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(12, 12).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0x1b222d }));
    floor.position.y = -0.002;
    this.ground.add(floor);
    this.scene.add(this.ground);

    this.camera.position.set(0.5, 1.15, 2.5);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0.75, 0);
    this.controls.update();
    this.controls.addEventListener("change", () => (this.dirty = true));
    this.controls.addEventListener("start", () => (this.userMoved = true));
  }

  /** Build the viewer in `el`: loads the meshes, creates the muscle tubes, subscribes to the timeline. */
  static async mount(el: HTMLElement, opts: Viewer3DOptions): Promise<Viewer3D> {
    const v = new Viewer3D(el, opts);
    await v.loadBones();
    v.buildMuscles();
    v.attach();
    v.update();
    v.frameSkeleton();
    return v;
  }

  // ---- construction ----
  private async loadBones(): Promise<void> {
    const base = this.opts.dataBase ?? "./";
    const index = parseMeshIndex(await (await fetch(`${base}meshes/index.json`)).json());
    for (const [body, places] of bodyPlacements(this.opts.query.allNodes())) this.bodyPlaces.set(body, places);
    const loader = new GLTFLoader();
    const bone = new THREE.MeshStandardMaterial({ color: 0xe9e2d0, roughness: 0.85, metalness: 0 });
    await Promise.all(
      index.bodies.map(async (b) => {
        const gltf = await loader.loadAsync(`${base}meshes/${b.file}`);
        gltf.scene.traverse((o) => {
          if ((o as THREE.Mesh).isMesh) (o as THREE.Mesh).material = bone;
        });
        const node = new THREE.Group();
        node.name = b.body;
        node.add(gltf.scene);
        node.matrixAutoUpdate = true;
        this.scene.add(node);
        this.bodyNodes.set(b.body, node);
      }),
    );
    this.ground.position.y = this.groundHeight();
  }

  /** The lowest point of the feet over the clip: the floor the walker stands on. */
  private groundHeight(): number {
    const clip = this.opts.timeline.clip;
    const box = new THREE.Box3();
    const corner = new THREE.Vector3();
    const q = new THREE.Quaternion();
    let low = Infinity;
    for (const body of ["calcn_r", "toes_r", "calcn_l", "toes_l"]) {
      const node = this.bodyNodes.get(body);
      const poses = clip.bodies.get(body);
      if (!node || !poses) continue;
      node.updateMatrixWorld(true);
      box.setFromObject(node);
      for (let f = 0; f < clip.time.length; f++) {
        q.set(poses[f * 7 + 3] ?? 0, poses[f * 7 + 4] ?? 0, poses[f * 7 + 5] ?? 0, poses[f * 7 + 6] ?? 1);
        for (let c = 0; c < 8; c++) {
          corner.set(c & 1 ? box.max.x : box.min.x, c & 2 ? box.max.y : box.min.y, c & 4 ? box.max.z : box.min.z);
          low = Math.min(low, corner.applyQuaternion(q).y + (poses[f * 7 + 1] ?? 0));
        }
      }
    }
    return Number.isFinite(low) ? low : 0;
  }

  private buildMuscles(): void {
    const clip = this.opts.timeline.clip;
    const nodeOf = (name: string) => this.opts.query.node(`muscle:${name}`);
    for (const plan of planBatches(clip.muscles.keys(), nodeOf)) {
      const tubes = plan.members.map((name): BatchTube => {
        const track = clip.muscles.get(name) as NonNullable<ReturnType<typeof clip.muscles.get>>;
        return {
          name,
          nodeId: `muscle:${name}`,
          frames: track.points.map((p) => resamplePath(p, new Float32Array(RINGS * 3))),
          activation: track.activation,
          velocity: track.velocity,
        };
      });
      const batch = new MuscleBatch(plan.key, tubes, this.tubeMaterial);
      this.scene.add(batch.mesh);
      this.batches.push(batch);
    }
  }

  private attach(): void {
    const { timeline } = this.opts;
    this.offs.push(timeline.onTime(() => (this.dirty = true)));
    this.offs.push(
      timeline.onSelect((id) => {
        this.selectedName = id?.startsWith("muscle:") ? id.slice("muscle:".length) : null;
        this.dirty = true;
      }),
    );
    this.selectedName = timeline.selectedId?.startsWith("muscle:") ? timeline.selectedId.slice(7) : null;
    if (this.opts.filter) this.offs.push(this.opts.filter.onChange(() => this.applyFilter()));
    this.applyFilter();

    const dom = this.renderer.domElement;
    let down: { x: number; y: number } | null = null;
    dom.addEventListener("pointerdown", (e) => (down = { x: e.clientX, y: e.clientY }));
    dom.addEventListener("pointerup", (e) => {
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 4) this.click(e);
      down = null;
    });
    dom.addEventListener("pointermove", (e) => (this.pendingHover = e));
    dom.addEventListener("pointerleave", () => (this.tooltip.style.display = "none"));

    const ro = new ResizeObserver(() => this.resize());
    ro.observe(this.el);
    this.offs.push(() => ro.disconnect());
    this.resize();
    const loop = () => {
      this.raf = requestAnimationFrame(loop);
      if (this.pendingHover) {
        const e = this.pendingHover;
        this.pendingHover = null;
        this.hover(e);
      }
      if (!this.dirty) return;
      this.dirty = false;
      this.update();
      this.renderer.render(this.scene, this.camera);
      this.countFrame();
    };
    this.raf = requestAnimationFrame(loop);
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    this.offs.forEach((f) => f());
    this.controls.dispose();
    this.renderer.dispose();
    this.el.innerHTML = "";
  }

  /** Put the camera where the bounds of every mesh in the mesh index fit the view, seen from the
   * side and slightly above. Call after `update()` so the bodies stand in the current pose. */
  frameSkeleton(): void {
    const boxes = [...this.bodyNodes.values()].map((node) => {
      node.updateMatrixWorld(true);
      const b = new THREE.Box3().setFromObject(node);
      return { min: [b.min.x, b.min.y, b.min.z] as const, max: [b.max.x, b.max.y, b.max.z] as const };
    });
    const bounds = unionBounds(boxes);
    if (!bounds) return;
    const fit = fitCamera(bounds, this.camera.fov, this.camera.aspect, FIT_MARGIN);
    const centre = new THREE.Vector3(...fit.centre);
    this.controls.target.copy(centre);
    this.camera.position.copy(centre).addScaledVector(VIEW_DIRECTION, fit.distance);
    this.camera.far = Math.max(this.camera.far, fit.distance * 4);
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.dirty = true;
  }

  // ---- per frame ----
  /** Pose the bones and rewrite the muscle tubes for the timeline's current time. */
  update(): void {
    const { clip, time } = this.opts.timeline;
    const { i0, i1, f } = frameAt(clip.time, time);
    for (const [body, node] of this.bodyNodes) {
      const p = clip.bodies.get(body);
      if (!p) continue;
      const a = i0 * 7;
      const b = i1 * 7;
      node.position.set(lerp(p[a], p[b], f), lerp(p[a + 1], p[b + 1], f), lerp(p[a + 2], p[b + 2], f));
      this.scratchA.set(p[a + 3] ?? 0, p[a + 4] ?? 0, p[a + 5] ?? 0, p[a + 6] ?? 1);
      this.scratchB.set(p[b + 3] ?? 0, p[b + 4] ?? 0, p[b + 5] ?? 0, p[b + 6] ?? 1);
      node.quaternion.slerpQuaternions(this.scratchA, this.scratchB, f);
      if (body === "pelvis") this.followPelvis(node.position.x);
    }
    const look = (t: BatchTube): TubeLook => {
      const selected = t.name === this.selectedName;
      return {
        radius: TUBE_RADIUS_M * (selected ? SELECTED_RADIUS_FACTOR : 1),
        opacityFactor: this.selectedName ? DIMMED_OPACITY_FACTOR : 1,
        solid: selected,
      };
    };
    for (const b of this.batches) b.update(i0, i1, f, look, this.scratch);
  }

  private followPelvis(x: number): void {
    if (this.lastPelvisX !== null) {
      const dx = x - this.lastPelvisX;
      this.camera.position.x += dx;
      this.controls.target.x += dx;
    }
    this.lastPelvisX = x;
    this.ground.position.x = Math.round(x / 0.5) * 0.5;
  }

  private countFrame(): void {
    this.frameCount++;
    const now = performance.now();
    if (now - this.fpsWindowStart >= 1000) {
      this.fps = (this.frameCount * 1000) / (now - this.fpsWindowStart);
      this.drawCalls = this.renderer.info.render.calls;
      if (DEV) {
        const line = fpsLine(this.fps, this.drawCalls, this.batches.filter((b) => b.mesh.visible).length, this.batches.reduce((n, b) => n + b.visibleCount, 0));
        if (this.fpsEl) this.fpsEl.textContent = line;
        console.info(`[bm] ${line}`);
      }
      this.frameCount = 0;
      this.fpsWindowStart = now;
    }
  }

  private resize(): void {
    const w = this.el.clientWidth || 1;
    const h = this.el.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (!this.userMoved && this.bodyNodes.size > 0) this.frameSkeleton();
    this.dirty = true;
  }

  /** Show the muscles and bones that pass the region filter. */
  private applyFilter(): void {
    const { filter, query } = this.opts;
    for (const b of this.batches) {
      b.setVisible((t) => {
        const node = query.node(t.nodeId);
        return !filter || !node || filter.passes(node);
      });
    }
    const sel = filter?.selection;
    for (const [body, node] of this.bodyNodes) node.visible = !sel || bodyPasses(sel, this.bodyPlaces.get(body));
    this.dirty = true;
  }

  // ---- picking ----
  private pick(e: PointerEvent): BatchTube | undefined {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const hit = this.raycaster.intersectObjects(this.batches.filter((b) => b.mesh.visible).map((b) => b.mesh), false)[0];
    return hit && this.batches.find((b) => b.mesh === hit.object)?.tubeAtFace(hit.faceIndex);
  }

  private click(e: PointerEvent): void {
    const tube = this.pick(e);
    if (tube && this.opts.query.node(tube.nodeId)) this.opts.timeline.select(tube.nodeId);
    else if (!tube) this.opts.timeline.clearSelection();
  }

  private hover(e: PointerEvent): void {
    const tube = this.pick(e);
    const node = tube && this.opts.query.node(tube.nodeId);
    const rect = this.el.getBoundingClientRect();
    this.renderer.domElement.style.cursor = node ? "pointer" : "";
    if (!tube) {
      this.tooltip.style.display = "none";
      return;
    }
    this.tooltip.textContent = node ? `${node.commonName ?? node.name} (${node.name})` : tube.name;
    this.tooltip.style.display = "block";
    this.tooltip.style.left = `${e.clientX - rect.left + 12}px`;
    this.tooltip.style.top = `${e.clientY - rect.top + 12}px`;
  }

  // ---- legend ----
  private buildLegend(): HTMLElement {
    const el = document.createElement("div");
    el.className = "bm-v-legend";
    el.style.cssText = "position:absolute;left:10px;bottom:10px;padding:8px 10px;border-radius:6px;background:rgba(10,12,16,.72);color:#e8ecf2;font:12px/1.4 system-ui;max-width:260px;";
    const sw = (w: WorkType) => `<span style="display:inline-block;width:14px;height:10px;border-radius:2px;margin-right:6px;background:${cssColour(muscleColour(0.8, w === "eccentric" ? 1 : w === "concentric" ? -1 : 0))}"></span>`;
    const ramp = (w: WorkType) => {
      const stops = [0, 0.25, 0.5, 0.75, 1].map((a) => cssColour(muscleColour(a, w === "eccentric" ? 1 : w === "concentric" ? -1 : 0)).replace(/ \/ [\d.]+\)/, ")")).join(",");
      return stops;
    };
    el.innerHTML = `
      <div style="font-weight:600;margin-bottom:4px">Muscle work</div>
      ${(["eccentric", "concentric", "isometric"] as const).map((w) => `<div>${sw(w)}${WORK_LABEL[w]}</div>`).join("")}
      <div style="margin-top:6px">Activation: dim and faint (0) to bright and solid (1)</div>
      <div style="height:8px;border-radius:2px;margin-top:3px;background:linear-gradient(90deg,${ramp("concentric")})"></div>
      <div style="opacity:.7;margin-top:4px">Scale: active above ${A_ACTIVE}; steady within ${V_ISOMETRIC} m/s; lightness ${L_MIN}-${L_MAX}; opacity ${OPACITY_MIN}-1.</div>`;
    return el;
  }
}
