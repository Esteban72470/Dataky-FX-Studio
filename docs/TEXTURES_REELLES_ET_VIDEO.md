# Textures and local video references

The catalogue keeps Roblox asset IDs and thumbnails, mostly at 420 × 420 pixels. A thumbnail contains no mesh geometry and cannot establish asset permissions. Use Roblox Studio for the final in-engine check.

The emulator can load original textures from `source/vfx/<effect>/textures/` using URIs of the form `rbxasset://textures/dataky-local/<effect>/<file>.png`. The server exposes these PNG files only. Scripts and other files under `source/` remain private to the local filesystem. Missing original textures are flagged and rendered transparent.

## Extract frames from video

**Références vidéo** (Video references) lets you import a local file, choose time windows, generate timestamped contact sheets, and add notes. The `tool/fx_video.py` module uses OpenCV, NumPy, and Pillow to decode and prepare the images.

```powershell
python -m pip install opencv-python numpy pillow
```

Suggested windows come from changes in motion, brightness, and colour. Quality levels A, B, and C control frame count and resolution. You can adjust segments manually and extract them again. Results are cached by the media fingerprint and extraction settings.

These measurements describe the video. The application uses no local model or vision call to critique the visuals. Notes saved with **Conserver les observations** (Save observations) are recorded as human observations.

Media, extracted frames, and caches stay under `editor/local_ai/video/`, a legacy local storage path excluded from Git. The editor stores a copy of each imported file. It does not download remote videos. Image routes serve only JPEGs listed in the analysis manifest.

The video tests use a synthetic video to check frame extraction, timestamps, caching, segment edits, annotations, and file access boundaries.
