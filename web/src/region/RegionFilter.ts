/**
 * RegionFilter: the state of the region and side selection, shared by the views.
 * A view reads `passes` when it draws and redraws on `onChange`; `mountRegionFilter`
 * (`RegionFilterControl.ts`) offers the checkboxes that change the state.
 */
import type { Region, Side } from "@gen/types";
import { everything, filterNodes, passes, type Placed, type RegionSelection } from "./groups";

export class RegionFilter {
  private regions: Set<Region>;
  private sides: Set<Side>;
  private readonly listeners = new Set<() => void>();

  constructor(initial: RegionSelection = everything()) {
    this.regions = new Set(initial.regions);
    this.sides = new Set(initial.sides);
  }

  /** The current selection (a copy). */
  get selection(): RegionSelection {
    return { regions: new Set(this.regions), sides: new Set(this.sides) };
  }

  passes(node: Placed): boolean {
    return passes({ regions: this.regions, sides: this.sides }, node);
  }

  filter<T extends Placed>(nodes: readonly T[]): T[] {
    return filterNodes({ regions: this.regions, sides: this.sides }, nodes);
  }

  get isEverything(): boolean {
    return this.regions.size === everything().regions.size && this.sides.size === everything().sides.size;
  }

  hasRegion(r: Region): boolean {
    return this.regions.has(r);
  }

  hasSide(s: Side): boolean {
    return this.sides.has(s);
  }

  setRegion(r: Region, on: boolean): void {
    if (on === this.regions.has(r)) return;
    if (on) this.regions.add(r);
    else this.regions.delete(r);
    this.emit();
  }

  setSide(s: Side, on: boolean): void {
    if (on === this.sides.has(s)) return;
    if (on) this.sides.add(s);
    else this.sides.delete(s);
    this.emit();
  }

  /** Select every region and side. */
  reset(): void {
    if (this.isEverything) return;
    const all = everything();
    this.regions = new Set(all.regions);
    this.sides = new Set(all.sides);
    this.emit();
  }

  /** Call `fn` after each change; returns the function that stops the calls. */
  onChange(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(): void {
    this.listeners.forEach((f) => f());
  }
}
