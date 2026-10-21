"""Package the native Studio bridge as a local, offline Roblox plugin."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

TOOL = Path(__file__).resolve().parent
LIBRARY = TOOL.parent


def package() -> Path:
    root = ET.Element("roblox", version="4")
    ET.SubElement(root, "External").text = "null"
    ET.SubElement(root, "External").text = "nil"
    main = ET.SubElement(root, "Item", {"class": "Script", "referent": "RBXDATAKYPLUGIN"})
    props = ET.SubElement(main, "Properties")
    ET.SubElement(props, "string", name="Name").text = "Dataky FX Studio"
    ET.SubElement(props, "ProtectedString", name="Source").text = (TOOL / "fx_plugin.lua").read_text(encoding="utf-8-sig")
    module = ET.SubElement(main, "Item", {"class": "ModuleScript", "referent": "RBXDATAKYRUNTIME"})
    props = ET.SubElement(module, "Properties")
    ET.SubElement(props, "string", name="Name").text = "Runtime"
    ET.SubElement(props, "ProtectedString", name="Source").text = (TOOL / "fx_runtime.lua").read_text(encoding="utf-8-sig")
    output = LIBRARY / "editor" / "DatakyFXStudio.rbxmx"
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Copy into this user's Roblox local Plugins folder")
    args = parser.parse_args()
    source = package()
    print("Plugin :", source)
    if args.install:
        appdata = os.environ.get("LOCALAPPDATA")
        if not appdata:
            raise SystemExit("LOCALAPPDATA est introuvable ; installation réservée à Windows.")
        target = Path(appdata) / "Roblox" / "Plugins" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            shutil.copy2(target, target.with_suffix(".rbxmx.bak"))
        shutil.copy2(source, target)
        print("Pont installé :", target)
        print("Redémarrez Roblox Studio pour charger ce plugin local.")
        print("Le bouton Studio de l’atelier propose aussi une connexion immédiate sans redémarrage.")


if __name__ == "__main__":
    main()
