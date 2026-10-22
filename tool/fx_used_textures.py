"""Write a bridge texture scan as an exclusion file, outside the catalogue."""
from pathlib import Path
import re

if __package__:
    from .fx_schema import ValidationError, text
    from .fx_server import atomic_bytes, confined
else:
    from fx_schema import ValidationError, text
    from fx_server import atomic_bytes, confined


def save_used_textures(library, place_name, ids):
    place_name = text(place_name, "place_name", 512, False)
    if not isinstance(ids, list) or len(ids) > 100_000:
        raise ValidationError("ids : liste de 100000 IDs maximum requise")
    clean = set()
    for value in ids:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,20}", value) or int(value) == 0:
            raise ValidationError("ids : IDs numériques positifs requis")
        clean.add(str(int(value)))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", place_name).strip(". ")[:120].rstrip(". ") or "Place"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    target = confined(Path(library) / "tool" / "used_textures", name + ".txt")
    ordered = sorted(clean, key=int)
    atomic_bytes(target, ("".join(value + "\n" for value in ordered)).encode("utf-8"))
    return {"path": str(target), "count": len(ordered), "place_name": place_name}
