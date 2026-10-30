/** Repository base URL for source links, e.g. "https://github.com/OWNER/REPO/blob/main". Empty: show `file:line` text.
 *  Proposed home: `web/src/config.ts` (App), passed to `mountArchitectureView` as an option. */
export const SOURCE_BASE_URL = "https://github.com/argent0/bio-mechanics/blob/main";

export function sourceLabel(loc: { file: string; line: number }): string { return `${loc.file}:${loc.line}`; }

export function sourceUrl(loc: { file: string; line: number }, base: string = SOURCE_BASE_URL): string | null {
  return base === "" ? null : `${base.replace(/\/$/, "")}/${loc.file}#L${loc.line}`;
}
