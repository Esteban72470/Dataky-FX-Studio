"""Download public Roblox thumbnail previews, with a verified resumable cache.

The files are Roblox-generated thumbnails, NOT original texture downloads.
Only requests and Pillow are required. This module never reads Roblox credentials.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import io
from pathlib import Path
import random
import re
import tempfile
import threading
import time
from urllib.parse import urlparse

import requests
from PIL import Image, ImageChops, ImageStat


API = "https://thumbnails.roblox.com/v1/assets"
_LOCAL = threading.local()
_MAX_BYTES = 12 * 1024 * 1024
_ID = re.compile(r"[1-9][0-9]{0,24}\Z")
_SIZES = {"150x150", "250x250", "420x420"}


class DownloadError(RuntimeError):
    pass


class _RateGate:
    """A 429 pauses the entire download pool, not just the requesting worker."""

    def __init__(self):
        self.lock = threading.Lock()
        self.until = 0.0

    def wait(self):
        while True:
            with self.lock:
                delay = self.until - time.monotonic()
            if delay <= 0:
                return
            time.sleep(min(delay, 1.0))

    def pause(self, seconds):
        with self.lock:
            self.until = max(self.until, time.monotonic() + seconds)


def _session():
    if not hasattr(_LOCAL, "session"):
        session = requests.Session()
        session.headers.update({"User-Agent": "ZonitoTextureLocalCatalogue/1.0"})
        _LOCAL.session = session
    return _LOCAL.session


def _retry_delay(header, attempt):
    delay = min(8.0, 1.0 * (2 ** attempt))
    if header:
        try:
            delay = float(header)
        except (ValueError, TypeError):
            try:
                date = parsedate_to_datetime(header)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                delay = (date - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                pass
    return min(30.0, max(1.0, delay)) + random.uniform(0, 0.3)


def _get(url, gate, params=None):
    """Bounded retries, streaming size limit, connection and read timeouts."""
    last_error = "request failed"
    for attempt in range(3):
        gate.wait()
        retry = False
        try:
            with _session().get(url, params=params, timeout=(8, 25), stream=True) as response:
                if response.status_code == 429:
                    gate.pause(_retry_delay(response.headers.get("Retry-After"), attempt))
                    last_error = "HTTP 429: Roblox rate limit"
                    retry = True
                elif response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}: service unavailable"
                    retry = True
                elif response.status_code != 200:
                    raise DownloadError(f"HTTP {response.status_code}")
                else:
                    size = int(response.headers.get("Content-Length", "0"))
                    if size > _MAX_BYTES:
                        raise DownloadError("response exceeds 12 MiB")
                    chunks = []
                    total = 0
                    for chunk in response.iter_content(65536):
                        total += len(chunk)
                        if total > _MAX_BYTES:
                            raise DownloadError("response exceeds 12 MiB")
                        chunks.append(chunk)
                    return b"".join(chunks)
        except requests.RequestException as exc:
            last_error = type(exc).__name__
            retry = True
        except ValueError:
            last_error = "invalid response header"
            retry = True
        if retry and attempt < 2:
            time.sleep(min(4.0, 0.8 * (2 ** attempt)) + random.uniform(0, 0.2))
    raise DownloadError(last_error)


def _open_verified(path):
    try:
        with Image.open(path) as image:
            if image.format != "PNG" or image.width <= 0 or image.height <= 0:
                return None
            if image.width * image.height > 16_777_216:
                return None
            image.load()
            return image.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _save_png(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.stem}-", suffix=".png", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            image.save(handle, format="PNG", optimize=False)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _metadata(ids, size, gate):
    import json
    raw = _get(API, gate, {"assetIds": ",".join(ids), "size": size, "format": "Png", "isCircular": "false"})
    try:
        data = json.loads(raw)
        rows = data["data"]
        if not isinstance(rows, list):
            raise ValueError("invalid data")
    except (ValueError, TypeError, KeyError) as exc:
        raise DownloadError("invalid thumbnail API response") from exc
    found = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        asset_id = str(row.get("targetId", ""))
        if asset_id in ids:
            found[asset_id] = row
    return found


def _safe_cdn_url(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (host == "rbxcdn.com" or host.endswith(".rbxcdn.com")) and not parsed.username and not parsed.password
    except (ValueError, TypeError):
        return False


def _download_image(asset_id, metadata, output_dir, gate):
    state = str(metadata.get("state", "Unavailable"))
    url = metadata.get("imageUrl")
    if state != "Completed" or not url:
        return {"image_status": state.lower(), "image_error": f"Roblox thumbnail state: {state}"}
    if not _safe_cdn_url(url):
        return {"image_status": "error", "image_error": "unexpected Roblox CDN URL"}
    try:
        raw = _get(url, gate)
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > 16_777_216:
                raise DownloadError("thumbnail dimensions exceed limit")
            source.load()
            image = source.convert("RGBA")
        path = output_dir / "images" / f"{asset_id}.png"
        _save_png(image, path)
        return {"image_status": "downloaded", "image_error": None, "image_path": path.relative_to(output_dir).as_posix(), "width": image.width, "height": image.height}
    except (DownloadError, OSError, ValueError, Image.DecompressionBombError) as exc:
        return {"image_status": "error", "image_error": str(exc)[:200]}


def _representative_frame(image_path, asset_id, grid, output_dir):
    """Keep the full thumbnail sheet; crop its most visible frame separately."""
    target = output_dir / "previews" / f"{asset_id}-{grid}x{grid}.png"
    existing = _open_verified(target) if target.is_file() else None
    if existing is not None and target.stat().st_mtime >= image_path.stat().st_mtime:
        return target.relative_to(output_dir).as_posix()
    image = _open_verified(image_path)
    if image is None or image.width < grid or image.height < grid:
        return None
    best = None
    best_score = -1
    for row in range(grid):
        for column in range(grid):
            frame = image.crop((column * image.width // grid, row * image.height // grid,
                                (column + 1) * image.width // grid, (row + 1) * image.height // grid))
            luminance = frame.convert("L")
            alpha = frame.getchannel("A")
            # Alpha supports dark sprites; luminance helps distinguish successive
            # bright frames when a thumbnail has an opaque black background.
            score = ImageStat.Stat(ImageChops.multiply(luminance, alpha)).mean[0] + ImageStat.Stat(alpha).mean[0] * 0.05
            if score > best_score:
                best_score, best = score, frame
    if best is not None:
        _save_png(best, target)
        return target.relative_to(output_dir).as_posix()
    return None


def download_previews(records: list[dict], output_dir: Path, workers: int = 12,
                      size: str = "420x420", retry_failed: bool = True) -> list[dict]:
    """Return copied records with local previews and honest per-image status.

    Network work is deduplicated by asset_id. Valid files are always reused.
    ``retry_failed=False`` also preserves previous terminal failures, if recorded.
    A second metadata pass retries Pending/temporary errors once when enabled.
    """
    if size not in _SIZES:
        raise ValueError(f"unsupported thumbnail size: {size}")
    workers = max(1, min(24, int(workers)))
    output_dir = Path(output_dir).resolve()
    (output_dir / "images").mkdir(parents=True, exist_ok=True)
    rows = [dict(row) for row in records]
    unique = {}
    for row in rows:
        asset_id = str(row.get("asset_id", ""))
        row["asset_id"] = asset_id
        row["image_source"] = f"Roblox thumbnail {size}"
        if not _ID.fullmatch(asset_id):
            row.update(image_status="invalid_id", image_error="asset_id must be a positive decimal ID", image_path=None, preview_path=None)
            continue
        unique.setdefault(asset_id, row)
    gate = _RateGate()
    outcomes = {}
    todo = []
    for asset_id, row in unique.items():
        path = output_dir / "images" / f"{asset_id}.png"
        image = _open_verified(path) if path.is_file() else None
        if image is not None:
            outcomes[asset_id] = {"image_path": path.relative_to(output_dir).as_posix(), "image_status": "cached", "image_error": None, "width": image.width, "height": image.height}
        elif not retry_failed and row.get("image_status") in {"error", "blocked", "unavailable", "inreview", "pending"}:
            outcomes[asset_id] = {"image_path": None, "image_status": row["image_status"], "image_error": row.get("image_error")}
        else:
            todo.append(asset_id)
    print(f"[images] {len(unique)} IDs uniques, {len(todo)} à télécharger, {len(outcomes)} déjà traités", flush=True)
    metadata = {}
    for pass_number in range(2 if retry_failed else 1):
        targets = todo if pass_number == 0 else [asset_id for asset_id in todo if metadata.get(asset_id, {}).get("state") in {None, "Pending", "TemporarilyUnavailable"}]
        if not targets:
            break
        if pass_number:
            time.sleep(2)
        batches = [targets[index:index + 100] for index in range(0, len(targets), 100)]
        with ThreadPoolExecutor(max_workers=min(3, len(batches))) as pool:
            futures = {pool.submit(_metadata, batch, size, gate): batch for batch in batches}
            for future in as_completed(futures):
                batch = futures[future]
                try:
                    found = future.result()
                    for asset_id in batch:
                        metadata[asset_id] = found.get(asset_id, {"state": "Pending"})
                except DownloadError as exc:
                    for asset_id in batch:
                        metadata[asset_id] = {"state": "TemporarilyUnavailable", "error": str(exc)}
        print(f"[images] métadonnées: passe {pass_number + 1}, {len(targets)} IDs", flush=True)
    completed = 0
    downloaded = 0
    failed = 0
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_download_image, asset_id, metadata.get(asset_id, {}), output_dir, gate): asset_id for asset_id in todo}
            for future in as_completed(futures):
                asset_id = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"image_status": "error", "image_error": type(exc).__name__}
                outcomes[asset_id] = result
                completed += 1
                if result["image_status"] == "downloaded":
                    downloaded += 1
                else:
                    failed += 1
                if completed % 100 == 0 or completed == len(todo):
                    print(f"[images] {completed}/{len(todo)}: {downloaded} téléchargées, {failed} indisponibles", flush=True)
    preview_cache = {}
    for row in rows:
        asset_id = row["asset_id"]
        if asset_id not in outcomes:
            continue
        # Clear stale paths/status before replacing them with this run's result.
        row.update(image_path=None, preview_path=None, image_error=None, width=None, height=None)
        row.update(outcomes[asset_id])
        if row["image_path"]:
            row["preview_path"] = row["image_path"]
            try:
                grid = int(row.get("grid") or 0)
            except (ValueError, TypeError):
                grid = 0
            if row.get("kind") == "flipbook" and grid in {2, 4, 8}:
                key = (asset_id, grid)
                if key not in preview_cache:
                    try:
                        preview_cache[key] = _representative_frame(output_dir / row["image_path"], asset_id, grid, output_dir)
                    except (OSError, ValueError) as exc:
                        preview_cache[key] = None
                        row["preview_error"] = str(exc)[:200]
                row["preview_path"] = preview_cache[key] or row["image_path"]
    return rows


def _selftest():
    """Small real-network test, plus cache and malformed-data checks."""
    import json
    ids = ["88372363219378", "17727455731", "17006059392", "17635381231"]
    records = [{"asset_id": value, "kind": "static", "grid": 0} for value in ids]
    records += [{"asset_id": ids[-1], "kind": "flipbook", "grid": 4}, {"asset_id": "../oops", "kind": "static"}]
    with tempfile.TemporaryDirectory(prefix="zonito-thumbnail-test-") as temporary:
        directory = Path(temporary)
        first = download_previews(records, directory, workers=4)
        assert all(row["image_status"] == "downloaded" for row in first[:-1]), first
        assert first[-1]["image_status"] == "invalid_id"
        assert len(list((directory / "images").glob("*.png"))) == 4
        assert (directory / first[-2]["preview_path"]).is_file()
        second = download_previews(first, directory, workers=4)
        assert all(row["image_status"] == "cached" for row in second[:-1])
        # A corrupted cache entry must be re-fetched, not counted as successful.
        (directory / "images" / f"{ids[0]}.png").write_bytes(b"not an image")
        third = download_previews(second[:1], directory, workers=1)
        assert third[0]["image_status"] == "downloaded", third
        print(json.dumps({"selftest": "passed", "network_ids": len(ids), "cache_reused": True, "corrupt_cache_repaired": True, "invalid_id_rejected": True, "flipbook_preview": True}))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test:
        _selftest()
    else:
        parser.print_help()
