"""Local sparse/adaptive video inspection, never an implicit VLM analysis.

The pipeline imports authorized local files, computes lightweight change metrics,
proposes candidate windows and extracts bounded timestamped contact sheets. It
does not download YouTube media, identify an attack with certainty, recover exact
Roblox parameters from pixels, or claim that a language model has seen frames.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
VERSION = 1
MAX_VIDEO_BYTES = 4 * 1024**3
EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}
LEVELS = {"A": {"max_frames": 8, "width": 320}, "B": {"max_frames": 16, "width": 480}, "C": {"max_frames": 32, "width": 640}}


class VideoError(ValueError):
    pass


def _dependencies():
    try:
        import cv2
        import numpy
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise VideoError("Analyse vidéo locale : OpenCV, NumPy et Pillow requis, dépendance absente : " + str(exc)) from None
    return cv2, numpy, Image, ImageDraw


def _root(root):
    return Path(ROOT if root is None else root).resolve()


def _directory(root, name):
    return _root(root) / "editor/local_ai/video" / name


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".video-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, allow_nan=False, indent=2)
            output.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024*1024):
            digest.update(block)
    return digest.hexdigest()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise VideoError("Identifiant vidéo SHA-256 attendu")
    return value


def _number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise VideoError(f"{label} : nombre fini compris entre {low} et {high} requis")
    return float(value)


def probe_video(path):
    """Read container-derived metadata; duration is frame_count / fps estimation."""
    cv2, _, _, _ = _dependencies()
    path = Path(path)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoError("Fichier vidéo illisible ou codec non pris en charge")
        width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps, count = capture.get(cv2.CAP_PROP_FPS), capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not (1 <= width <= 16384 and 1 <= height <= 16384 and math.isfinite(fps) and 0 < fps <= 1000 and math.isfinite(count) and count > 0):
            raise VideoError("Métadonnées vidéo invalides ou durée non disponible")
        duration = count / fps
        if duration <= 0 or duration > 48*3600:
            raise VideoError("Vidéo limitée à 48 heures")
        readable, _ = capture.read()
        if not readable:
            raise VideoError("Aucune image vidéo décodable")
        return {"width": width, "height": height, "fps": fps, "frame_count": int(count),
                "duration_seconds": duration, "duration_source": "opencv_frame_count_divided_by_fps",
                "timestamp_source": "opencv_CAP_PROP_POS_MSEC_after_decode", "codec_backend": capture.getBackendName()}
    finally:
        capture.release()


def import_video(path, *, root=None, source_url="", rights_note=""):
    """Copy a legally provided local video into a persistent content-addressed store."""
    if not isinstance(path, (str, Path)) or str(path).startswith(("http://", "https://")):
        raise VideoError("Chemin local requis ; aucun téléchargement de vidéo distante")
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
        raise VideoError("Fichier vidéo local mp4/webm/mov/mkv/avi/m4v requis")
    if not 0 < path.stat().st_size <= MAX_VIDEO_BYTES:
        raise VideoError("Fichier vidéo local limité à 4 Gio")
    for value, label, limit in ((source_url, "source_url", 2000), (rights_note, "rights_note", 4000)):
        if not isinstance(value, str) or len(value) > limit:
            raise VideoError(label + " : texte court requis")
    if source_url and not source_url.startswith(("https://", "http://")):
        raise VideoError("source_url HTTP(S) attendue")
    digest = _hash_file(path)
    folder = _directory(root, "references")
    folder.mkdir(parents=True, exist_ok=True)
    index = folder / (digest + ".json")
    if index.is_file():
        existing = json.loads(index.read_text(encoding="utf-8"))
        stored = _root(root) / existing["relative_path"]
        if stored.is_file() and _hash_file(stored) == digest:
            return existing
    metadata = probe_video(path)
    target = folder / (digest + path.suffix.lower())
    fd, temporary = tempfile.mkstemp(prefix=".video-import-", suffix=path.suffix, dir=folder)
    os.close(fd)
    try:
        shutil.copyfile(path, temporary)
        if _hash_file(Path(temporary)) != digest:
            raise VideoError("Le fichier vidéo a changé pendant l'import")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    record = {"version": VERSION, "id": digest, "sha256": digest, "name": path.name,
              "relative_path": target.relative_to(_root(root)).as_posix(), "bytes": target.stat().st_size,
              "metadata": metadata, "source_url": source_url, "rights_note": rights_note,
              "created_at": datetime.now(timezone.utc).isoformat(), "source_kind": "user_local_file",
              "content_observed_by_model": False}
    _atomic(index, record)
    return record


def get_video(reference_id, *, root=None):
    ident = _id(reference_id)
    path = _directory(root, "references") / (ident + ".json")
    if not path.is_file():
        raise VideoError("Vidéo locale non importée")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        candidate = (_root(root) / value["relative_path"]).resolve()
    except (ValueError, KeyError, TypeError):
        raise VideoError("Index de vidéo invalide") from None
    allowed = _directory(root, "references").resolve()
    if not candidate.is_relative_to(allowed) or candidate.stem != ident or candidate.suffix.lower() not in EXTENSIONS:
        raise VideoError("Chemin de vidéo importée invalide")
    if not candidate.is_file():
        raise VideoError("Le fichier vidéo importé est manquant")
    if _hash_file(candidate) != ident:
        raise VideoError("La vidéo importée a changé ; réimporter le nouveau fichier")
    return deepcopy(value)


def list_videos(*, root=None):
    folder = _directory(root, "references")
    values = []
    if folder.exists():
        for path in folder.glob("*.json"):
            try:
                values.append(get_video(path.stem, root=root))
            except VideoError:
                continue
    return sorted(values, key=lambda value: value.get("created_at", ""), reverse=True)


def _read_at(capture, seconds, cv2):
    capture.set(cv2.CAP_PROP_POS_MSEC, seconds*1000)
    ok, frame = capture.read()
    if not ok:
        return None
    measured = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
    if not math.isfinite(measured) or measured < 0:
        measured = seconds
    return frame, measured


def _signature(frame, cv2, numpy):
    tiny = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(tiny, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(tiny, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([tiny], [0, 1, 2], None, [4, 4, 4], [0, 256]*3).flatten()
    hist = hist / max(1, hist.sum())
    ahash = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    bits = ahash >= ahash.mean()
    digest = "".join(f"{int(''.join('1' if v else '0' for v in bits.flatten()[i:i+4]), 2):x}" for i in range(0, 64, 4))
    return {"gray": gray, "hist": hist, "brightness": float(gray.mean()) / 255,
            "color": [float(v) / 255 for v in rgb.mean(axis=(0, 1))], "hash": digest}


def _changes(current, previous, numpy):
    if previous is None:
        return {"motion": 0.0, "brightness_change": 0.0, "color_change": 0.0, "cut_candidate": False, "score": 0.0}
    motion = float(numpy.abs(current["gray"].astype(float)-previous["gray"].astype(float)).mean()) / 255
    brightness = abs(current["brightness"]-previous["brightness"])
    color = float(numpy.abs(current["hist"]-previous["hist"]).sum()) / 2
    return {"motion": motion, "brightness_change": brightness, "color_change": color,
            "cut_candidate": color > .45 and motion > .15, "score": min(1.0, motion*.5 + brightness*.25 + color*.25)}


def _manual_segments(values, duration):
    if not isinstance(values, list) or not 1 <= len(values) <= 32:
        raise VideoError("1 à 32 segments manuels requis")
    segments = []
    for index, value in enumerate(values):
        if not isinstance(value, dict) or set(value)-{"start", "end", "label", "phases"}:
            raise VideoError("Segment : start, end, label et phases uniquement")
        start = _number(value.get("start"), "segment.start", 0, duration)
        end = _number(value.get("end"), "segment.end", start, duration)
        if end <= start or end-start > 120:
            raise VideoError("Segment manuel de durée positive et de 120 secondes maximum requis")
        label = value.get("label", f"Segment manuel {index+1}")
        if not isinstance(label, str) or len(label) > 160:
            raise VideoError("label court requis")
        phases = value.get("phases", [])
        if not isinstance(phases, list) or len(phases) > 16:
            raise VideoError("phases : 16 annotations maximum")
        clean_phases = []
        for phase in phases:
            if not isinstance(phase, dict) or set(phase) != {"name", "start", "end"} or not isinstance(phase["name"], str) or len(phase["name"]) > 80:
                raise VideoError("Phase : name, start, end requis")
            a = _number(phase["start"], "phase.start", start, end)
            b = _number(phase["end"], "phase.end", a, end)
            clean_phases.append({"name": phase["name"], "start": a, "end": b, "source": "manual"})
        segments.append({"id": f"segment-{index+1}", "start": start, "end": end, "label": label,
                         "source": "manual", "validation": "human_timestamps", "phases": clean_phases})
    return segments


def _candidate_segments(samples, duration, interval):
    if len(samples) <= 1:
        return [{"id": "segment-1", "start": 0.0, "end": min(duration, 10.0), "label": "Extrait à examiner",
                 "source": "heuristic", "validation": "required", "phases": [], "score": 0.0}]
    values = sorted(sample["score"] for sample in samples)
    threshold = max(.07, values[min(len(values)-1, int(len(values)*.75))])
    peaks = sorted((sample for sample in samples if sample["score"] >= threshold), key=lambda sample: -sample["score"])
    regions = []
    for sample in peaks:
        start, end = max(0, sample["timestamp"]-interval), min(duration, sample["timestamp"]+interval*1.5)
        if any(start <= region["end"] and end >= region["start"] for region in regions):
            continue
        regions.append({"start": start, "end": end, "score": sample["score"]})
        if len(regions) >= 12:
            break
    if not regions:
        regions = [{"start": 0.0, "end": min(duration, max(5, interval*3)), "score": 0.0}]
    regions.sort(key=lambda region: region["start"])
    for index, region in enumerate(regions):
        region.update(id=f"segment-{index+1}", label=f"Candidat visuel {index+1}", source="heuristic", validation="required", phases=[])
    return regions


def _select_frames(capture, segment, level, cv2, numpy):
    duration = segment["end"]-segment["start"]
    budget = LEVELS[level]["max_frames"]
    # Spend more frames on longer or more active sequences, never one identical
    # fixed number for every candidate. Endpoints and peak changes are retained.
    complexity = float(segment.get("score", .3))
    wanted = min(budget, max(4, math.ceil(math.sqrt(duration)*3 + complexity*budget)))
    probes = min(96, max(wanted*3, math.ceil(duration*4)))
    times = [segment["start"]+duration*i/(probes-1) for i in range(probes)]
    frames, previous = [], None
    for requested in times:
        decoded = _read_at(capture, max(segment["start"], requested-.00001), cv2)
        if decoded is None:
            continue
        frame, timestamp = decoded
        signature = _signature(frame, cv2, numpy)
        changes = _changes(signature, previous, numpy)
        previous = signature
        frames.append({"frame": frame, "timestamp": timestamp, "requested_timestamp": requested,
                       "signature": signature, **changes})
    if not frames:
        raise VideoError("Aucune image du segment n'est décodable")
    # Always preserve endpoints; choose strongest changes and temporal coverage.
    chosen = {0, len(frames)-1}
    ranked = sorted(range(1, len(frames)-1), key=lambda i: (-frames[i]["score"], i))
    min_gap = max(.025, duration/(wanted*3))
    for index in ranked:
        if len(chosen) >= wanted:
            break
        candidate = frames[index]
        repeated = any(candidate["signature"]["hash"] == frames[i]["signature"]["hash"] and abs(candidate["timestamp"]-frames[i]["timestamp"]) < duration*.4 for i in chosen)
        if repeated and candidate["score"] < .03:
            continue
        if all(abs(candidate["timestamp"]-frames[i]["timestamp"]) >= min_gap for i in chosen):
            chosen.add(index)
    if len(chosen) < min(4, wanted, len(frames)):
        for index in range(0, len(frames), max(1, len(frames)//wanted)):
            chosen.add(index)
            if len(chosen) >= min(4, wanted):
                break
    return [frames[i] for i in sorted(chosen)], len(frames), wanted


def _sheets(frame_records, folder, level, Image, ImageDraw):
    paths = []
    tile_width = LEVELS[level]["width"]
    for page, start in enumerate(range(0, len(frame_records), 16)):
        batch = frame_records[start:start+16]
        columns = 2 if len(batch) <= 4 else 3 if len(batch) <= 9 else 4
        rows = math.ceil(len(batch)/columns)
        image = Image.new("RGB", (columns*tile_width, rows*(round(tile_width*9/16)+26)), (18, 17, 25))
        draw = ImageDraw.Draw(image)
        for index, item in enumerate(batch):
            x, y = index % columns * tile_width, index // columns * (round(tile_width*9/16)+26)
            with Image.open(folder / item["file"]) as source:
                thumb = source.convert("RGB")
                thumb.thumbnail((tile_width, round(tile_width*9/16)))
                image.paste(thumb, (x+(tile_width-thumb.width)//2, y+26))
            draw.text((x+7, y+5), f"{item['timestamp']:.3f} s", fill=(240, 236, 250))
        filename = f"contact-sheet-{page+1}.jpg"
        image.save(folder / filename, quality=91)
        paths.append(filename)
    return paths


def analyze_video(reference_id, *, root=None, level="A", sample_interval=3, max_samples=1800, segments=None):
    """Run local heuristics and bounded adaptive extraction, with a persistent cache."""
    if level not in LEVELS:
        raise VideoError("level A, B ou C requis")
    sample_interval = _number(sample_interval, "sample_interval", .25, 30)
    if type(max_samples) is not int or not 2 <= max_samples <= 4000:
        raise VideoError("max_samples : entier de 2 à 4000 requis")
    reference = get_video(reference_id, root=root)
    duration = reference["metadata"]["duration_seconds"]
    manual = _manual_segments(segments, duration) if segments is not None else None
    parameters = {"version": VERSION, "sha256": reference["sha256"], "level": level,
                  "sample_interval": sample_interval, "max_samples": max_samples, "segments": manual}
    analysis_id = hashlib.sha256(json.dumps(parameters, sort_keys=True, allow_nan=False).encode()).hexdigest()
    folder = _directory(root, "analyses") / analysis_id
    manifest = folder / "analysis.json"
    if manifest.is_file():
        cached = json.loads(manifest.read_text(encoding="utf-8"))
        if all((folder / frame["file"]).is_file() for frame in cached["selected_frames"]) and all((folder / sheet).is_file() for sheet in cached["contact_sheets"]):
            return {**cached, "cache_hit": True}
    started = time.perf_counter()
    cv2, numpy, Image, ImageDraw = _dependencies()
    path = _root(root) / reference["relative_path"]
    capture = cv2.VideoCapture(str(path))
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if not capture.isOpened():
            raise VideoError("Vidéo importée devenue illisible")
        actual_interval = max(sample_interval, duration/max(1, max_samples-1))
        times = [min(duration-.00001, i*actual_interval) for i in range(min(max_samples, math.floor(duration/actual_interval)+1))]
        samples, previous = [], None
        for requested in times:
            decoded = _read_at(capture, max(0, requested), cv2)
            if decoded is None:
                continue
            frame, timestamp = decoded
            signature = _signature(frame, cv2, numpy)
            changes = _changes(signature, previous, numpy)
            previous = signature
            samples.append({"timestamp": timestamp, "requested_timestamp": requested,
                            "brightness": signature["brightness"], "mean_rgb": signature["color"],
                            "perceptual_hash": signature["hash"], **changes})
        if not samples:
            raise VideoError("Aucune image lors de l'échantillonnage léger")
        candidates = manual if manual is not None else _candidate_segments(samples, duration, actual_interval)
        selected = []
        extraction_probes = 0
        for segment in candidates:
            frames, probes, budget = _select_frames(capture, segment, level, cv2, numpy)
            extraction_probes += probes
            segment["selected_frame_budget"] = budget
            segment["selected_frame_count"] = len(frames)
            for item in frames:
                filename = f"{segment['id']}-frame-{len(selected)+1:04d}.jpg"
                frame = cv2.cvtColor(item["frame"], cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame)
                image.thumbnail((LEVELS[level]["width"]*2, LEVELS[level]["width"]*2))
                image.save(folder / filename, quality=94)
                selected.append({"segment": segment["id"], "timestamp": item["timestamp"],
                                 "requested_timestamp": item["requested_timestamp"], "file": filename,
                                 "information_score": item["score"], "perceptual_hash": item["signature"]["hash"]})
        selected.sort(key=lambda item: (item["timestamp"], item["segment"]))
        for index, frame in enumerate(selected):
            frame["delta_previous_seconds"] = None if index == 0 else frame["timestamp"]-selected[index-1]["timestamp"]
        sheets = _sheets(selected, folder, level, Image, ImageDraw)
        result = {"version": VERSION, "id": analysis_id, "reference_id": reference["id"], "level": level,
                  "created_at": datetime.now(timezone.utc).isoformat(), "relative_directory": folder.relative_to(_root(root)).as_posix(),
                  "metadata": reference["metadata"], "parameters": parameters, "samples": samples,
                  "segments": candidates, "selected_frames": selected, "contact_sheets": sheets,
                  "metrics": {"elapsed_seconds": round(time.perf_counter()-started, 4), "sparse_images": len(samples),
                              "adaptive_images_examined": extraction_probes, "selected_images": len(selected), "contact_sheet_count": len(sheets),
                              "multimodal_calls": 0, "multimodal_tokens": None},
                  "artistic_analysis": {"status": "not_analyzed_by_model", "observations": [], "hypotheses": [], "human_validation_required": True},
                  "limitations": ["Brightness, motion and scene changes are candidate heuristics, not proof of an attack.",
                                  "Sparse scans can miss an event shorter than the sampling interval; manual windows remain available.",
                                  "Timestamps are OpenCV decoder positions; duration metadata is an estimate for variable-frame-rate sources.",
                                  "A/B/C control local sampling/detail budgets; no visual language model analysis has been performed.",
                                  "Contact sheets do not imply proportionally fewer model tokens; token cost is unknown until measured.",
                                  "Exact Roblox object configurations cannot be recovered from reference pixels alone."], "cache_hit": False}
        _atomic(manifest, result)
        return result
    finally:
        capture.release()


def get_analysis(analysis_id, *, root=None):
    ident = _id(analysis_id)
    path = _directory(root, "analyses") / ident / "analysis.json"
    if not path.is_file():
        raise VideoError("Analyse vidéo introuvable")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("id") != ident:
        raise VideoError("Index d'analyse incohérent")
    return value


def annotate_analysis(analysis_id, observations, *, root=None):
    """Persist explicitly human notes separately from immutable extraction data."""
    ident = _id(analysis_id)
    get_analysis(ident, root=root)
    fields = {"concept", "palette", "silhouette", "motion", "timing", "impact", "technique_hypotheses", "notes"}
    if not isinstance(observations, dict) or not observations or set(observations)-fields:
        raise VideoError("Observations humaines : champs concept, palette, silhouette, motion, timing, impact, technique_hypotheses, notes")
    cleaned = {}
    for key, value in observations.items():
        if not isinstance(value, str) or not value.strip() or len(value) > 4000 or "\x00" in value:
            raise VideoError("Observation humaine non vide de 4000 caractères maximum requise")
        cleaned[key] = value.strip()
    record = {"id": uuid.uuid4().hex, "analysis_id": ident, "observer": "human",
              "created_at": datetime.now(timezone.utc).isoformat(), "observations": cleaned,
              "technical_implementation_recovered": False}
    _atomic(_directory(root, "analyses") / ident / "annotations" / (record["id"]+".json"), record)
    return record


def list_annotations(analysis_id, *, root=None):
    ident = _id(analysis_id)
    get_analysis(ident, root=root)
    folder = _directory(root, "analyses") / ident / "annotations"
    records = []
    if folder.exists():
        for path in folder.glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if value.get("analysis_id") == ident and value.get("observer") == "human":
                    records.append(value)
            except (ValueError, OSError, TypeError):
                continue
    return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)


def list_analyses(*, root=None):
    folder = _directory(root, "analyses")
    values = []
    if folder.exists():
        for path in folder.glob("*/analysis.json"):
            try:
                value = get_analysis(path.parent.name, root=root)
                values.append({key: value[key] for key in ("id", "reference_id", "level", "created_at", "metrics", "segments", "contact_sheets", "relative_directory")})
            except (VideoError, ValueError, KeyError):
                continue
    return sorted(values, key=lambda value: value["created_at"], reverse=True)
