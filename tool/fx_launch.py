"""Open or run the local Dataky editor. No model, credentials or cloud service."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import socket
import urllib.error
import urllib.request
import webbrowser


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--port', type=int, default=48754)
    parser.add_argument('--no-browser', action='store_true')
    args, remaining = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    if not 0 <= args.port <= 65535:
        print('Le port doit être compris entre 0 et 65535.')
        return 1
    root = Path(__file__).resolve().parent.parent
    chosen = None
    for port in range(args.port, min(args.port + 11, 65536)):
        base = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(base + "/api/status", timeout=.4) as response:
                status = json.load(response)
            if status.get('app') == 'Dataky FX Studio' and status.get('library') and Path(status['library']).resolve() == root:
                if not args.no_browser:
                    webbrowser.open(base + '/')
                print('Cette copie de Dataky FX Studio est déjà ouverte : ' + base)
                return 0
        except (ValueError, OSError, TimeoutError):
            pass
        try:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
            chosen = port
            break
        except OSError:
            continue
    if chosen is None:
        print('Aucun port local libre ; utilisez --port avec un autre port.')
        return 1
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fx_server
    return fx_server.main(['--port', str(chosen), *(['--no-browser'] if args.no_browser else []), *remaining])


if __name__ == "__main__":
    raise SystemExit(main())
