#!/usr/bin/env python3
"""Run the Dash UI application.

Usage:
    python scripts/run_dash.py
    python scripts/run_dash.py --port 8050
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.presentation.dash_app.app import create_dash_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Event Manager Dash UI")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8050, help="Bind port")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    app = create_dash_app()
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
