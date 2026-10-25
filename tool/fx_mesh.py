"""Bounded, data-only OBJ import for the local preview, separate from Roblox IDs.

No material files, URLs, scripts or external resources are opened. Geometry is
centred and normalized per axis; the original dimensions become MeshPart.Size.
Publish/import the OBJ manually in Studio and explicitly set MeshId for export.
"""
from __future__ import annotations

import hashlib
import math
import re

MAX_OBJ_BYTES = 4 * 1024 * 1024
MAX_TRIANGLES = 20_000
MAX_VERTICES = 60_000
MAX_MESHES = 32
MAX_TOTAL_TRIANGLES = 100_000
MAX_TOTAL_JSON_BYTES = 16 * 1024 * 1024


class MeshError(ValueError):
    pass


def _fail(message):
    raise MeshError(message)


def _finite(value, bound=1_000_000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > bound:
        _fail("coordonnée finie bornée requise")
    return float(value)


def _normal(v):
    length = math.hypot(*v)
    if length < 1e-12:
        _fail("normale nulle ou face dégénérée")
    return [x / length for x in v]


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def validate_mesh(mesh):
    """Validate explicit indexed geometry, without accepting arbitrary metadata."""
    if not isinstance(mesh, dict) or set(mesh) != {"version", "positions", "normals", "uvs", "indices", "source"}:
        _fail("géométrie attendue : version, positions, normals, uvs, indices, source")
    if type(mesh["version"]) is not int or mesh["version"] != 1:
        _fail("version de géométrie 1 requise")
    positions, normals, uvs, indices = (mesh[k] for k in ("positions", "normals", "uvs", "indices"))
    if not isinstance(positions, list) or not 9 <= len(positions) <= MAX_VERTICES * 3 or len(positions) % 3:
        _fail("positions : 3 à 60000 sommets requis")
    count = len(positions) // 3
    if not isinstance(normals, list) or len(normals) != count * 3:
        _fail("normals : une normale par sommet requise")
    if not isinstance(uvs, list) or len(uvs) != count * 2:
        _fail("uvs : deux coordonnées par sommet requises")
    if not isinstance(indices, list) or not 3 <= len(indices) <= MAX_TRIANGLES * 3 or len(indices) % 3:
        _fail("indices : 1 à 20000 triangles requis")
    for values, bound in ((positions, 0.500001), (normals, 1.000001), (uvs, 10000)):
        for value in values:
            _finite(value, bound)
    for i in range(0, len(normals), 3):
        if abs(math.hypot(*normals[i:i+3]) - 1) > 0.001:
            _fail("normals : vecteurs unitaires requis")
    if any(type(i) is not int or not 0 <= i < count for i in indices):
        _fail("indices : entier dans les bornes des sommets requis")
    source = mesh["source"]
    if not isinstance(source, dict) or set(source) != {"name", "format", "sha256", "dimensions"}:
        _fail("source invalide")
    if not isinstance(source["name"], str) or not 1 <= len(source["name"]) <= 160 or any(ord(c) < 32 for c in source["name"]):
        _fail("source.name : texte court requis")
    if source["format"] != "obj" or not isinstance(source["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", source["sha256"]):
        _fail("source OBJ avec empreinte SHA-256 requise")
    dimensions = source["dimensions"]
    if not isinstance(dimensions, list) or len(dimensions) != 3:
        _fail("source.dimensions : trois nombres requis")
    for value in dimensions:
        if _finite(value, 2048) < 0:
            _fail("dimensions positives ou nulles requises")
    return mesh


def import_obj(text, node_id="imported_mesh", *, name="mesh.obj", mesh_id=""):
    """Return {node, mesh, warnings}; callers merge mesh into editor.meshes[id]."""
    if not isinstance(text, str) or len(text) > MAX_OBJ_BYTES or len(text.encode("utf-8")) > MAX_OBJ_BYTES:
        _fail("OBJ limité à 4 Mio de texte UTF-8")
    if not isinstance(node_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", node_id):
        _fail("node_id invalide")
    if not isinstance(name, str) or not 1 <= len(name) <= 160 or any(ord(c) < 32 for c in name):
        _fail("nom OBJ court requis")
    if not isinstance(mesh_id, str) or (mesh_id and not re.fullmatch(r"(?:rbxassetid://)?[1-9][0-9]*", mesh_id)):
        _fail("MeshId Roblox numérique attendu")
    vertices, texcoords, supplied_normals, faces = [], [], [], []
    warnings = set()
    triangle_count = 0
    lines = text.splitlines()
    if len(lines) > 100_000:
        _fail("OBJ limité à 100000 lignes")
    for line_number, original in enumerate(lines, 1):
        if len(original) > 16384:
            _fail(f"ligne {line_number} : 16384 caractères maximum")
        words = original.partition("#")[0].split()
        if not words:
            continue
        directive, args = words[0], words[1:]
        try:
            if directive == "v":
                if len(args) not in (3, 4):
                    _fail("v : trois coordonnées et w optionnel requis")
                values = [_finite(float(a)) for a in args]
                if len(values) == 4:
                    if abs(values[3]) < 1e-12:
                        _fail("v : w non nul requis")
                    values = [_finite(v / values[3]) for v in values[:3]]
                vertices.append(values)
            elif directive == "vt":
                if len(args) not in (2, 3):
                    _fail("vt : deux coordonnées requises")
                texcoords.append([_finite(float(v), 10000) for v in args[:2]])
            elif directive == "vn":
                if len(args) != 3:
                    _fail("vn : trois coordonnées requises")
                supplied_normals.append(_normal([_finite(float(v)) for v in args]))
            elif directive == "f":
                if not 3 <= len(args) <= 64:
                    _fail("face : 3 à 64 sommets requis")
                def index(token, pool):
                    if not re.fullmatch(r"-?[0-9]+", token):
                        _fail("index OBJ entier requis")
                    n = int(token)
                    resolved = n - 1 if n > 0 else len(pool) + n
                    if n == 0 or not 0 <= resolved < len(pool):
                        _fail("index OBJ hors bornes")
                    return resolved
                face = []
                for token in args:
                    parts = token.split("/")
                    if len(parts) > 3 or not parts[0]:
                        _fail("référence de face invalide")
                    face.append((index(parts[0], vertices), index(parts[1], texcoords) if len(parts) > 1 and parts[1] else None,
                                 index(parts[2], supplied_normals) if len(parts) > 2 and parts[2] else None))
                faces.append(face)
                triangle_count += len(face) - 2
                if triangle_count > MAX_TRIANGLES:
                    _fail("OBJ limité à 20000 triangles")
            elif directive in {"mtllib", "usemtl"}:
                warnings.add("Matériaux OBJ/MTL ignorés ; aucune ressource externe n'est ouverte. Utiliser TextureID et Color dans l'éditeur.")
            elif directive == "s":
                warnings.add("Groupes de lissage ignorés ; normales explicites conservées, normales manquantes calculées par face.")
            elif directive in {"o", "g"}:
                pass
            elif directive in {"l", "p"}:
                warnings.add("Lignes et points OBJ ignorés ; seules les surfaces triangulées sont importées.")
            else:
                _fail("directive OBJ non prise en charge : " + directive[:40])
            if max(len(vertices), len(texcoords), len(supplied_normals)) > MAX_VERTICES:
                _fail("OBJ limité à 60000 éléments par canal")
        except (ValueError, OverflowError) as error:
            raise MeshError(f"ligne {line_number} : {error}") from error
    if not faces:
        _fail("OBJ sans surface : au moins une face requise")
    used = {ref[0] for face in faces for ref in face}
    low = [min(vertices[j][i] for j in used) for i in range(3)]
    high = [max(vertices[j][i] for j in used) for i in range(3)]
    dimensions = [high[i] - low[i] for i in range(3)]
    if max(dimensions) > 2048:
        _fail("dimensions OBJ supérieures à 2048 ; réduire l'échelle du fichier avant import")
    center = [(low[i] + high[i]) / 2 for i in range(3)]
    divisor = [d if d > 1e-10 else 1 for d in dimensions]
    positions, normals, uvs, indices, lookup = [], [], [], [], {}
    for face_number, face in enumerate(faces):
        points = [vertices[ref[0]] for ref in face]
        # Newell normal supports convex planar n-gons, including collinear edges.
        n = [0.0, 0.0, 0.0]
        for i, a in enumerate(points):
            b = points[(i + 1) % len(points)]
            n[0] += (a[1]-b[1])*(a[2]+b[2]); n[1] += (a[2]-b[2])*(a[0]+b[0]); n[2] += (a[0]-b[0])*(a[1]+b[1])
        n = _normal(n)
        tolerance = max(max(dimensions), 1) * 1e-6
        for i, point in enumerate(points):
            if abs(sum(n[k]*(point[k]-points[0][k]) for k in range(3))) > tolerance:
                _fail("face non plane ; trianguler dans le logiciel source")
            cross = _cross(_sub(points[(i+1) % len(points)], point), _sub(points[(i+2) % len(points)], points[(i+1) % len(points)]))
            if sum(cross[k] * n[k] for k in range(3)) < -tolerance:
                _fail("face concave ; trianguler dans le logiciel source")
        local = []
        for ref in face:
            key = (ref[0], ref[1], ref[2] if ref[2] is not None else -(face_number + 1))
            if key not in lookup:
                lookup[key] = len(positions) // 3
                if lookup[key] >= MAX_VERTICES:
                    _fail("géométrie dépliée limitée à 60000 sommets")
                positions.extend((vertices[ref[0]][i] - center[i]) / divisor[i] for i in range(3))
                original_normal = supplied_normals[ref[2]] if ref[2] is not None else n
                normals.extend(_normal([original_normal[i] * divisor[i] for i in range(3)]))
                # HTML images use top-left texture origin; OBJ UVs use bottom-left.
                uv = texcoords[ref[1]] if ref[1] is not None else [0, 0]
                uvs.extend([uv[0], 1 - uv[1]])
            local.append(lookup[key])
        for j in range(1, len(local) - 1):
            indices.extend((local[0], local[j], local[j+1]))
    mesh = {"version": 1, "positions": positions, "normals": normals, "uvs": uvs, "indices": indices,
            "source": {"name": name, "format": "obj", "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "dimensions": dimensions}}
    validate_mesh(mesh)
    properties = {"Position": [0, 2, 0], "Orientation": [0, 0, 0], "Size": [max(0.001, d) for d in dimensions],
                  "Transparency": 0, "Color": [1, 1, 1], "Material": "SmoothPlastic", "Anchored": True,
                  "CanCollide": False, "CanTouch": False, "CanQuery": False, "DoubleSided": False, "MeshId": mesh_id}
    if not mesh_id:
        warnings.add("Aperçu local uniquement : importer le fichier dans Roblox Studio puis renseigner son MeshId avant export Roblox.")
    return {"node": {"id": node_id, "class": "MeshPart", "name": name, "parent": None, "properties": properties},
            "mesh": mesh, "warnings": sorted(warnings)}
