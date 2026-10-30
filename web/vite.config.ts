import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const gen = fileURLToPath(new URL("../generated/ts", import.meta.url));
const data = fileURLToPath(new URL("../data", import.meta.url));

export default defineConfig({
  // Relative base: the build serves from any subpath (GitHub Pages).
  base: "./",
  resolve: { alias: { "@gen": gen } },
  // Pipeline output (data/out/: graph.json, meshes/, muscle_paths.json) is served
  // and shipped as static files at the site root, fetched at run time.
  publicDir: fileURLToPath(new URL("../data/out", import.meta.url)),
  // The app reads ../generated and ../data, outside the web/ root.
  server: { fs: { allow: [fileURLToPath(new URL("..", import.meta.url)), data] } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
