# Portable reference notes

This guide records the behaviour of the former local AI memory module. The current editor uses manual art direction.

`tool/fx_ai_memory.py` stored explicit observations and found relevant references through text search. It did not create effects, train the model, or reconstruct Roblox properties from video.

## Sources and provenance

- Explicit references include the source URL, description, optional phases and timestamps, palette, tags, and notes. They are stored in `editor/local_ai/knowledge.json` with an ID and provenance.
- Human video annotations already stored under `editor/local_ai/video/analyses/<id>/annotations/` are read without modification. Analysis and reference IDs, URLs, and time windows stay in the retrieved context. Analysis phases count as artistic phases only when marked as manual.
- Acceptance and rejection feedback under `editor/local_ai/feedback/` is linked to the generation. The module keeps the most recent explicit feedback for each result and attributes comments to the user. Accepting one purple effect does not imply a general preference for purple. A rejection without a reason stays unexplained.

The module never inferred video annotations from brightness changes or extracted images alone. An external `observer="vision"` annotation required textual evidence from its author. The module kept it as a reported observation without claiming to have run a vision model or verified pixels.

The module treated sources and notes as reference data. Current user instructions took precedence. Unknown techniques and undocumented rights stayed unknown, and the module fetched no external resources.

## API

```python
from tool import fx_ai_memory as memory

record = memory.add_reference({
    "source_url": "https://example.org/reference",
    "description": "A narrow cyan blade followed by a thinner trail",
    "tags": ["sword", "slash"],
    "phases": [{"name": "impact", "start": 0.5, "end": 0.7}],
    "notes": "Human observation: the flash does not obscure the blade edge."
}, root=application_folder, observer="human")

context = memory.search("cyan slash with a clear impact", root=application_folder, limit=4)
```

`search` returns `items`, `method="lexical"`, `counts`, `revision`, `total_matches`, `warnings`, and `limitations`. The SHA-256 revision reflects the data that was actually read. Each request rereads the sources, so recent annotations and feedback are available without restarting.

## Limits and verification

Search uses names, descriptions, tags, notes, observations, and simple French and English synonyms. It uses no embeddings or visual similarity score. Adding local vectors would require a measurement protocol and explicit cache invalidation.

Each search returns up to eight references and bounds the excerpts supplied to the model. Full notes stay on disk. The registry supports 512 references and 8 MiB. For external sources, it reads up to the 512 newest files per category and warns if a limit is reached. The module never rewrites external analyses or feedback.

The index uses atomic writes and an interprocess lock. It surfaces invalid JSON in the explicit index and warns before skipping corrupt external sources. Relative paths and IDs make the application and its references portable together.

`tool/test_fx_ai_memory.py` covered provenance, invalid timestamps, unsupported vision notes, human video annotations, feedback scope, read-only access to sources, portability, and four concurrent writers. The tests did not feed predefined VFX recipes to the model.
