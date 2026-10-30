/** DOM controls of the Timeline: play/pause, stop, speed, scrub bar, and the seven phase bands. */
import * as gait from "@gen/gaitFsm";
import { SPEEDS, type Timeline } from "./Timeline";

const SWING_START = gait.PHASES.indexOf(gait.step("preSwing", "toeOff"));
/** Stance phases stand before the phase that toe-off opens; swing phases from it on. */
const isSwing = (p: gait.GaitPhase): boolean => gait.PHASES.indexOf(p) >= SWING_START;

const CSS = `
.bm-tl { font: 13px system-ui, sans-serif; display: grid; gap: 6px; padding: 8px 12px; }
.bm-tl-row { display: flex; gap: 8px; align-items: center; }
.bm-tl button, .bm-tl select { font: inherit; padding: 3px 10px; }
.bm-tl-scrub { position: relative; }
.bm-tl-scrub input[type=range] { width: 100%; margin: 0; position: relative; z-index: 1; background: transparent; }
.bm-tl-bands { display: flex; height: 44px; border-radius: 4px; overflow: hidden; margin-top: 2px; }
.bm-tl-band { box-sizing: border-box; padding: 3px 5px; overflow: hidden; border-right: 1px solid rgba(255,255,255,.7); line-height: 1.15; cursor: pointer; }
.bm-tl-band b { display: block; font-weight: 600; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
.bm-tl-band small { display: block; opacity: .75; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; font-size: 11px; }
.bm-tl-band[data-swing="false"] { background: #d6e2f0; color: #1d3550; }
.bm-tl-band[data-swing="true"] { background: #d5ebe2; color: #174031; }
.bm-tl-band[data-current="true"] { background: #1d4f91; color: #fff; }
.bm-tl-band[data-swing="true"][data-current="true"] { background: #1b7a57; }
.bm-tl-read { margin-left: auto; font-variant-numeric: tabular-nums; color: #444; }
`;

function ensureStyle(doc: Document): void {
  if (doc.getElementById("bm-tl-style")) return;
  const style = doc.createElement("style");
  style.id = "bm-tl-style";
  style.textContent = CSS;
  doc.head.append(style);
}

/** Mount the controls in `el` and start the playback clock; returns a function that removes the controls and stops the clock. */
export function mountTimeline(el: HTMLElement, timeline: Timeline): () => void {
  ensureStyle(el.ownerDocument);
  el.classList.add("bm-tl");
  el.innerHTML = `
    <div class="bm-tl-row">
      <button data-act="play" aria-label="Play">Play</button>
      <button data-act="stop" aria-label="Stop and rewind">Stop</button>
      <label>Speed <select data-act="speed">${SPEEDS.map((s) => `<option value="${s}"${s === timeline.speed ? " selected" : ""}>${s}x</option>`).join("")}</select></label>
      <label><input type="checkbox" data-act="loop"${timeline.loop ? " checked" : ""}> Loop</label>
      <span class="bm-tl-read" data-act="read"></span>
    </div>
    <div class="bm-tl-scrub">
      <input type="range" min="0" max="1000" step="1" value="0" aria-label="Position in the stride" data-act="scrub">
      <div class="bm-tl-bands"></div>
    </div>`;
  const q = <T extends HTMLElement>(act: string) => el.querySelector(`[data-act=${act}]`) as T;
  const playBtn = q<HTMLButtonElement>("play");
  const range = q<HTMLInputElement>("scrub");
  const read = q<HTMLElement>("read");
  const bandsEl = el.querySelector(".bm-tl-bands") as HTMLElement;

  const bandEls = timeline.bands.map((b) => {
    const d = el.ownerDocument.createElement("div");
    d.className = "bm-tl-band";
    d.style.width = `${b.endPct - b.startPct}%`;
    d.dataset["swing"] = String(isSwing(b.gaitPhase));
    d.title = `${b.plainName} (${b.name}), ${b.startPct.toFixed(0)}-${b.endPct.toFixed(0)} % of the stride`;
    d.innerHTML = `<b></b><small></small>`;
    (d.firstElementChild as HTMLElement).textContent = b.plainName;
    (d.lastElementChild as HTMLElement).textContent = b.name;
    d.addEventListener("click", () => {
      timeline.scrubStart();
      timeline.scrubTo(b.startPct);
      timeline.scrubEnd();
    });
    bandsEl.append(d);
    return d;
  });

  const refreshState = () => {
    playBtn.textContent = timeline.state === "playing" ? "Pause" : "Play";
  };
  const refreshTime = () => {
    range.value = String(Math.round(timeline.pct * 10));
    read.textContent = `${timeline.pct.toFixed(0)} % of the stride · ${timeline.phase.plainName}`;
    bandEls.forEach((d, i) => (d.dataset["current"] = String(timeline.bands[i] === timeline.phase)));
  };

  playBtn.addEventListener("click", () => (timeline.state === "playing" ? timeline.pause() : timeline.play()));
  q("stop").addEventListener("click", () => timeline.stop());
  q<HTMLSelectElement>("speed").addEventListener("change", (e) => timeline.setSpeed(Number((e.target as HTMLSelectElement).value)));
  q<HTMLInputElement>("loop").addEventListener("change", (e) => (timeline.loop = (e.target as HTMLInputElement).checked));
  // Pointer drags and key presses both arrive as `input`; `change` closes the gesture.
  range.addEventListener("input", () => {
    if (timeline.state !== "scrubbing") timeline.scrubStart();
    timeline.scrubTo(Number(range.value) / 10);
  });
  range.addEventListener("change", () => timeline.scrubEnd());

  const offs = [timeline.onUi(refreshState), timeline.onTime(refreshTime)];
  refreshState();
  refreshTime();
  const stopClock = timeline.startClock();
  return () => {
    stopClock();
    offs.forEach((f) => f());
    el.innerHTML = "";
  };
}
