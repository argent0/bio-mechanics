"""Stage `exportMeshes`: one glTF file per lower-body bone segment, from the model's `.vtp` meshes.

Bodies: `BODIES`, the pelvis and both legs (pelvis, femur, patella, tibia, talus, calcn, toes).
Each body's meshes are the `.vtp` files attached to it (`model.json` `bodies[].geometry`), read
from the geometry directory (`pipeline_paths.GEOMETRY`) and multiplied per axis by the mesh's
scale factors. The scale factors come from the scaled model (`pipeline_paths.SCALED_MODEL`,
element `Mesh/scale_factors`): `model.json` lists the mesh files without them. Every mesh of
this model hangs directly on its body frame (`socket_frame` ".."), so mesh coordinates are body
coordinates.

VTP reading (`read_vtp`): VTK XML PolyData with ASCII data arrays (the format of every file of
the Rajagopal geometry): `Points` (float triples) and `Polys` (`connectivity`, `offsets`);
polygons with more than three corners are split into triangle fans. Vertex normals are the
area-weighted mean of the adjacent face normals.

glTF (`gltf_document`): glTF 2.0, one `.gltf` per body with its buffer embedded as a base64
data URI; one mesh with one primitive per `.vtp` file (attributes `POSITION`, `NORMAL`, uint16
or uint32 `indices`), one node per primitive's mesh, all in the body frame: metres, y up, the
OpenSim body axes unchanged (x forward, z to the right in the model's default pose).

Output `data/out/meshes/index.json` (the web viewer's entry point):
  format      "bm-meshes/1"
  units       "m"
  bodies      [{body, file, meshes: [{file, scaleFactors}], vertices, triangles}], in `BODIES`
              order; `file` is the glTF file name beside index.json
  transforms  {file, key}: where the per-frame body poses live: `muscle_paths.json` (beside the
              meshes directory) under `bodies`; there each body has, per frame, the pose of its
              frame in ground as [px, py, pz, qx, qy, qz, qw] (position in m, unit quaternion in
              glTF order). A viewer places a body's glTF node at that position and rotation.

Run from the repository root: `python -m pipeline.export_meshes` (pure Python).
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import struct
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.load_model import REPO
from pipeline.segment_phases import GENERATED

import pipeline_paths as paths  # noqa: E402  (generated/py: see `GENERATED`)

BODIES = (
    "pelvis",
    "femur_r", "patella_r", "tibia_r", "talus_r", "calcn_r", "toes_r",
    "femur_l", "patella_l", "tibia_l", "talus_l", "calcn_l", "toes_l",
)
"""The bodies exported: pelvis and both legs."""

FORMAT = "bm-meshes/1"

Vec3 = tuple[float, float, float]


@dataclass
class Mesh:
    """Triangles of one surface: vertex positions and normals, and corner indices."""

    positions: list[Vec3]
    normals: list[Vec3]
    triangles: list[tuple[int, int, int]]


def _numbers(el: ET.Element | None) -> list[str]:
    if el is None or el.text is None:
        return []
    return el.text.split()


def read_vtp(path: Path, scale: Vec3 = (1.0, 1.0, 1.0)) -> Mesh:
    """Points and polygons of an ASCII VTK PolyData file, scaled per axis by `scale`."""
    root = ET.parse(path).getroot()
    piece = root.find("PolyData/Piece")
    if piece is None:
        raise ValueError(f"{path}: no PolyData piece")
    for arr in piece.iter("DataArray"):
        if arr.get("format", "ascii") != "ascii":
            raise ValueError(f"{path}: data array format {arr.get('format')}; ASCII expected")
    xyz = [float(v) for v in _numbers(piece.find("Points/DataArray"))]
    positions = [(xyz[i] * scale[0], xyz[i + 1] * scale[1], xyz[i + 2] * scale[2]) for i in range(0, len(xyz), 3)]
    conn = [int(v) for v in _numbers(piece.find("Polys/DataArray[@Name='connectivity']"))]
    offs = [int(v) for v in _numbers(piece.find("Polys/DataArray[@Name='offsets']"))]
    tris: list[tuple[int, int, int]] = []
    start = 0
    for end in offs:
        poly = conn[start:end]
        tris += [(poly[0], poly[k], poly[k + 1]) for k in range(1, len(poly) - 1)]
        start = end
    # A negative determinant of the scaling mirrors the surface; keep the winding outward.
    if scale[0] * scale[1] * scale[2] < 0:
        tris = [(a, c, b) for a, b, c in tris]
    return Mesh(positions, vertex_normals(positions, tris), tris)


def vertex_normals(p: Sequence[Vec3], tris: Sequence[tuple[int, int, int]]) -> list[Vec3]:
    """Area-weighted mean of the face normals around each vertex, normalised."""
    acc = [[0.0, 0.0, 0.0] for _ in p]
    for a, b, c in tris:
        u = [p[b][i] - p[a][i] for i in range(3)]
        v = [p[c][i] - p[a][i] for i in range(3)]
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        for k in (a, b, c):
            for i in range(3):
                acc[k][i] += n[i]
    out: list[Vec3] = []
    for x, y, z in acc:
        norm = math.sqrt(x * x + y * y + z * z) or 1.0
        out.append((x / norm, y / norm, z / norm))
    return out


def _f32(x: float) -> float:
    """`x` rounded to float32, as the buffer stores it (accessor bounds must match)."""
    v: float = struct.unpack("<f", struct.pack("<f", x))[0]
    return v


def _pad4(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def gltf_document(name: str, meshes: Sequence[tuple[str, Mesh]]) -> dict[str, Any]:
    """A glTF 2.0 document with one primitive per named mesh and an embedded buffer."""
    FLOAT, U16, U32 = 5126, 5123, 5125
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
    blob = b""
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    primitives: list[dict[str, Any]] = []

    def add_view(data: bytes, target: int) -> int:
        nonlocal blob
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob += _pad4(data)
        return len(views) - 1

    for _, m in meshes:
        pos = struct.pack(f"<{3 * len(m.positions)}f", *(c for v in m.positions for c in v))
        nrm = struct.pack(f"<{3 * len(m.normals)}f", *(c for v in m.normals for c in v))
        flat = [i for t in m.triangles for i in t]
        wide = len(m.positions) > 65535
        idx = struct.pack(f"<{len(flat)}{'I' if wide else 'H'}", *flat)
        lo = [_f32(min(v[i] for v in m.positions)) for i in range(3)]
        hi = [_f32(max(v[i] for v in m.positions)) for i in range(3)]
        accessors.append({"bufferView": add_view(pos, ARRAY_BUFFER), "componentType": FLOAT, "count": len(m.positions), "type": "VEC3", "min": lo, "max": hi})
        p_acc = len(accessors) - 1
        accessors.append({"bufferView": add_view(nrm, ARRAY_BUFFER), "componentType": FLOAT, "count": len(m.normals), "type": "VEC3"})
        n_acc = len(accessors) - 1
        accessors.append({"bufferView": add_view(idx, ELEMENT_ARRAY_BUFFER), "componentType": U32 if wide else U16, "count": len(flat), "type": "SCALAR"})
        primitives.append({"attributes": {"POSITION": p_acc, "NORMAL": n_acc}, "indices": len(accessors) - 1, "mode": 4})
    return {
        "asset": {"version": "2.0", "generator": "pipeline.export_meshes"},
        "scene": 0,
        "scenes": [{"name": name, "nodes": [0]}],
        "nodes": [{"name": name, "mesh": 0}],
        "meshes": [{"name": name, "primitives": primitives, "extras": {"sources": [f for f, _ in meshes]}}],
        "buffers": [{"byteLength": len(blob), "uri": "data:application/octet-stream;base64," + base64.b64encode(blob).decode()}],
        "bufferViews": views,
        "accessors": accessors,
    }


def mesh_scale_factors(osim_path: Path) -> dict[tuple[str, str], Vec3]:
    """(body, mesh file) -> scale factors, from the `Mesh` elements of an `.osim` file."""
    out: dict[tuple[str, str], Vec3] = {}
    root = ET.parse(osim_path).getroot()
    for body in root.iter("Body"):
        name = body.get("name", "")
        for mesh in body.iterfind("attached_geometry/Mesh"):
            frame = (mesh.findtext("socket_frame") or "..").strip()
            if frame != "..":
                raise ValueError(f"{name}: mesh on frame {frame}; meshes on the body frame expected")
            f = (mesh.findtext("mesh_file") or "").strip()
            s = [float(v) for v in (mesh.findtext("scale_factors") or "1 1 1").split()]
            out[(name, f)] = (s[0], s[1], s[2])
    return out


def run(model_json: Path, geometry: Path, osim: Path, out: Path) -> list[dict[str, Any]]:
    model = json.loads(model_json.read_text())
    geometry_of = {b["name"]: b["geometry"] for b in model["bodies"]}
    scales = mesh_scale_factors(osim)
    out.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for body in BODIES:
        meshes = [(f, read_vtp(geometry / f, scales[(body, f)])) for f in geometry_of[body]]
        file = f"{body}.gltf"
        (out.parent / file).write_text(json.dumps(gltf_document(body, meshes), separators=(",", ":")))
        entries.append(
            {
                "body": body,
                "file": file,
                "meshes": [{"file": f, "scaleFactors": list(scales[(body, f)])} for f, _ in meshes],
                "vertices": sum(len(m.positions) for _, m in meshes),
                "triangles": sum(len(m.triangles) for _, m in meshes),
            }
        )
    index = {
        "format": FORMAT,
        "units": "m",
        "bodies": entries,
        "transforms": {"file": "../muscle_paths.json", "key": "bodies"},
    }
    out.write_text(json.dumps(index, indent=1) + "\n")
    return entries


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="python -m pipeline.export_meshes", description=doc.split("\n")[0])
    ap.add_argument("--model", type=Path, default=REPO / paths.MODEL, help="model.json")
    ap.add_argument("--geometry", type=Path, default=REPO / paths.GEOMETRY)
    ap.add_argument("--osim", type=Path, default=REPO / paths.SCALED_MODEL, help="scaled model (mesh scale factors)")
    ap.add_argument("--out", type=Path, default=REPO / paths.MESHES)
    a = ap.parse_args(argv)
    entries = run(a.model, a.geometry, a.osim, a.out)
    print(f"export_meshes: {len(entries)} bodies, {sum(e['triangles'] for e in entries)} triangles; wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
