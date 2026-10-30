import type { Kind } from "@gen/types";

/** Colour of each node kind, shared by the graph nodes and their icons. */
export const COLOURS: Record<Kind, string> = {
  bone: "#b8b8b8", joint: "#e0a030", muscle: "#d05050", muscleGroup: "#e08080",
  ligament: "#70a060", nerve: "#e0d040", movement: "#4060c0", phase: "#6080e0", jointAction: "#40a0c0",
};

/** Glyph of each node kind: SVG markup on a 16×16 grid, drawn in the kind's colour
 * (`currentColor`). A new `Kind` in `spec/BioMech/Schema.lean` makes `tsc` ask for its glyph. */
const GLYPHS: Record<Kind, string> = {
  // A long bone: shaft with a knob at each end.
  bone: '<rect x="5" y="6.5" width="6" height="3" rx="1"/><circle cx="4" cy="6" r="2"/><circle cx="4" cy="10" r="2"/><circle cx="12" cy="6" r="2"/><circle cx="12" cy="10" r="2"/>',
  // A ball in its socket.
  joint: '<circle cx="8" cy="7" r="3.5"/><path d="M2.5 8.5a5.5 5.5 0 0 0 11 0" fill="none" stroke="currentColor" stroke-width="1.6"/>',
  // A spindle-shaped muscle belly with tendons.
  muscle: '<path d="M1.5 8C4 3.5 12 3.5 14.5 8 12 12.5 4 12.5 1.5 8Z"/><path d="M0 8h1.5M14.5 8H16" stroke="currentColor" stroke-width="1.4"/>',
  // Three bellies side by side.
  muscleGroup: '<ellipse cx="4" cy="8" rx="2.2" ry="6"/><ellipse cx="8" cy="8" rx="2.2" ry="6"/><ellipse cx="12" cy="8" rx="2.2" ry="6"/>',
  // A band that crosses between two bones.
  ligament: '<rect x="1" y="1" width="14" height="3" rx="1.5" opacity=".45"/><rect x="1" y="12" width="14" height="3" rx="1.5" opacity=".45"/><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  // A trunk that branches.
  nerve: '<path d="M8 15V7M8 7 3 2M8 7l5-5M8 10 4 7M8 10l4-3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  // Two footprints.
  movement: '<ellipse cx="5" cy="10" rx="2.3" ry="3.6"/><ellipse cx="11" cy="5.5" rx="2.3" ry="3.6"/>',
  // A clock face with one sector: a slice of the cycle.
  phase: '<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 8V1.5A6.5 6.5 0 0 1 14 5.5Z"/>',
  // A curved arrow: rotation about a joint.
  jointAction: '<path d="M3 12A6 6 0 1 1 13 9.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M10 9.5h5l-2.5 3.5Z"/>',
};

/** An inline icon for a node kind, with the kind name as its accessible label. */
export function kindIcon(kind: Kind): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("fill", "currentColor");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", kind);
  svg.classList.add("kind-icon");
  svg.style.color = COLOURS[kind];
  svg.innerHTML = `<title>${kind}</title>${GLYPHS[kind]}`;
  return svg;
}
