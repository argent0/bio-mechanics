/**
 * Search over the nodes of every region. A pure function of the nodes and the text.
 *
 * Matching: the text splits into words; a node matches when every word occurs in its anatomical
 * name, common name, id, or place (region and side, "whole body" for a movement or phase). "knee" finds the knees of both legs, "left knee"
 * the left one, "trunk muscle" the muscles of the trunk. Order: names equal to the whole text
 * first, then names that start with its first word, then the rest, each in graph order.
 */
import type { Node } from "@gen/types";
import { groupHeading, type Placed } from "../region";

const WORDS = /[\s,·]+/;

const words = (text: string): string[] => text.toLowerCase().split(WORDS).filter(Boolean);

/** Where a node sits, in words: "Lower limb, right", or "Whole body" for a movement or phase. */
export function placeLabel(n: Placed): string {
  return groupHeading(n.region, n.side);
}

function haystack(n: Node): string {
  return [n.name, n.commonName ?? "", n.id, placeLabel(n)].join(" ").toLowerCase();
}

/** Nodes that match `text`, best first; `pass` leaves out the nodes outside a region filter. */
export function searchNodes(nodes: readonly Node[], text: string, pass: (n: Placed) => boolean = () => true): Node[] {
  const ws = words(text);
  if (ws.length === 0) return [];
  const whole = ws.join(" ");
  const rank = (n: Node): number => {
    const names = [n.name, n.commonName ?? ""].map((s) => s.toLowerCase());
    if (names.includes(whole)) return 0;
    return names.some((s) => s.startsWith(ws[0]!)) ? 1 : 2;
  };
  return nodes
    .filter((n) => pass(n) && ws.every((w) => haystack(n).includes(w)))
    .map((n, i) => ({ n, i, r: rank(n) }))
    .sort((a, b) => a.r - b.r || a.i - b.i)
    .map((x) => x.n);
}

export interface SearchOption {
  /** Text to offer as a suggestion; it names the node and its place on the body. */
  value: string;
  node: Node;
}

/** One suggestion per node: "vastus lateralis · Lower limb, left". Left and right differ. */
export function searchOptions(nodes: readonly Node[]): SearchOption[] {
  return nodes.map((node) => ({ value: `${node.commonName ?? node.name} · ${placeLabel(node)}`, node }));
}
