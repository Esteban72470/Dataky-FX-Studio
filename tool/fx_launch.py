"""Open or run the local Dataky editor. No model, credentials or cloud service."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
import webbrowser


def main() -> int:
    base = "http://127.0.0.1:48754"
    try:
        with urllib.request.urlopen(base + "/api/status", timeout=1) as response:
            status = json.load(response)
        if status.get("app") != "Dataky FX Studio":
            print("Le port 48754 est occupé par une autre application.")
            return 1
        webbrowser.open(base + "/")
        print("Dataky FX Studio est déjà ouvert : " + base)
        return 0
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        pass
    except (ValueError, OSError) as error:
        print("Impossible de vérifier l’atelier local :", error)
        return 1
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fx_server
    return fx_server.main()


if __name__ == "__main__":
    raise SystemExit(main())
