import { Viewer3D, type Viewer3DOptions } from "./Viewer3D";

export { Viewer3D, type Viewer3DOptions };
export { muscleColour, workType, type WorkType, type MuscleColour } from "./colour";

/** Mount the 3D view in `el` (give `el` a height). */
export function mountViewer3D(el: HTMLElement, opts: Viewer3DOptions): Promise<Viewer3D> {
  return Viewer3D.mount(el, opts);
}
