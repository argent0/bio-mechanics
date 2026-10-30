/** The checkboxes of a `RegionFilter`: one per region, one per side, and a button that selects all. */
import { REGION, SIDE, type Region, type Side } from "@gen/types";
import { REGION_LABEL, SIDE_LABEL, SIDE_ORDER } from "./groups";
import type { RegionFilter } from "./RegionFilter";

const CSS = `
.bm-rf { font: 12px/1.4 system-ui, sans-serif; display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: center; }
.bm-rf fieldset { border: 0; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; }
.bm-rf legend { float: left; padding: 0 6px 0 0; font-weight: 600; }
.bm-rf label { white-space: nowrap; cursor: pointer; }
`;

/** Mount the checkboxes in `el`; the returned function removes them. */
export function mountRegionFilter(el: HTMLElement, filter: RegionFilter): () => void {
  const doc = el.ownerDocument;
  if (!doc.getElementById("bm-rf-style")) doc.head.append(Object.assign(doc.createElement("style"), { id: "bm-rf-style", textContent: CSS }));
  el.classList.add("bm-rf");
  const box = (kind: "region" | "side", value: string, label: string) =>
    `<label><input type="checkbox" data-${kind}="${value}"> ${label}</label>`;
  el.innerHTML = `
    <fieldset><legend>Region</legend>${REGION.map((r) => box("region", r, REGION_LABEL[r])).join("")}</fieldset>
    <fieldset><legend>Side</legend>${SIDE_ORDER.map((s) => box("side", s, SIDE_LABEL[s])).join("")}</fieldset>
    <button type="button" data-all>all</button>`;
  const sync = () => {
    el.querySelectorAll<HTMLInputElement>("input[data-region]").forEach((i) => (i.checked = filter.hasRegion(i.dataset["region"] as Region)));
    el.querySelectorAll<HTMLInputElement>("input[data-side]").forEach((i) => (i.checked = filter.hasSide(i.dataset["side"] as Side)));
    el.querySelector<HTMLButtonElement>("button[data-all]")!.disabled = filter.isEverything;
  };
  const onInput = (e: Event) => {
    const t = e.target as HTMLInputElement;
    if (t.dataset["region"]) filter.setRegion(t.dataset["region"] as Region, t.checked);
    if (t.dataset["side"] && SIDE.includes(t.dataset["side"] as Side)) filter.setSide(t.dataset["side"] as Side, t.checked);
  };
  const onClick = (e: Event) => {
    if ((e.target as HTMLElement).closest("[data-all]")) filter.reset();
  };
  el.addEventListener("input", onInput);
  el.addEventListener("click", onClick);
  const off = filter.onChange(sync);
  sync();
  return () => {
    off();
    el.removeEventListener("input", onInput);
    el.removeEventListener("click", onClick);
    el.innerHTML = "";
  };
}
