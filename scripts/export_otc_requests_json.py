#!/usr/bin/env python3
"""
SOST Gold Exchange — OTC Requests Export

Reads OTC requests from data/otc_requests.json (if present) and produces
formatted JSON for the web dashboard.

Currently a placeholder — OTC functionality is coming in a future phase.

Usage:
  python3 scripts/export_otc_requests_json.py
  python3 scripts/export_otc_requests_json.py --output /opt/sost/website/api/otc_requests.json
"""

import json
import os
import sys
import argparse
import time

_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_this_dir)


def load_otc_requests(path: str) -> list:
    """Load OTC requests from JSON file. Returns empty list if missing."""
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "requests" in data:
                return data["requests"]
        except Exception as e:
            print(f"Warning: failed to load OTC requests from {path}: {e}",
                  file=sys.stderr)
    return []


def export_otc_requests(requests: list) -> dict:
    """Format OTC requests into the web API structure."""
    return {
        "generated_at": time.time(),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_requests": len(requests),
        "note": "OTC desk coming soon — operator-assisted block trades for qualified participants",
        "requests": requests,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export SOST OTC requests to JSON API format"
    )
    parser.add_argument(
        "--requests",
        default=os.path.join(_project_root, "data", "otc_requests.json"),
        help="Path to otc_requests.json (default: data/otc_requests.json)",
    )
    parser.add_argument(
        "--output", default="",
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    requests = load_otc_requests(args.requests)
    result = export_otc_requests(requests)
    output_json = json.dumps(result, indent=2) + "\n"

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        tmp_path = args.output + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                f.write(output_json)
            os.replace(tmp_path, args.output)
            print(f"Exported {result['total_requests']} OTC requests to {args.output}",
                  file=sys.stderr)
        except Exception as e:
            print(f"Error writing to {args.output}: {e}", file=sys.stderr)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            sys.exit(1)
    else:
        sys.stdout.write(output_json)


if __name__ == "__main__":
    main()
