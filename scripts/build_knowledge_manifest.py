"""Validate a knowledge tree and build an immutable S3 release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from khyati.knowledge.sources import validate_document


def build_manifest(source: Path, version: str, release_prefix: str) -> dict:
    files = [
        path for path in sorted(source.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}
    ]
    if not files:
        raise ValueError(f"No Markdown or text knowledge found in {source}")
    prefix = release_prefix.strip("/")
    documents = []
    for path in files:
        relative = path.relative_to(source).as_posix()
        payload = path.read_bytes()
        validate_document(relative, payload.decode("utf-8"))
        documents.append({
            "path": relative,
            "key": f"{prefix}/{relative}",
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    return {"version": version, "documents": documents}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.source, args.version, args.release_prefix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {len(manifest['documents'])} documents; wrote {args.output}")


if __name__ == "__main__":
    main()
