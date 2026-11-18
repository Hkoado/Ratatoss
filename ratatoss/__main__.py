"""Run the local node, or work with manifests on the command line."""

import argparse
import sys
from pathlib import Path

from .manifest import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_PIECE_SIZE,
    Manifest,
    build_manifest,
    verify_batch,
    verify_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="ratatoss")
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Run the loopback UI")
    serve.add_argument("--port", type=int, default=8765)
    create = commands.add_parser("manifest", help="Create a manifest")
    create.add_argument("file", type=Path)
    create.add_argument("-o", "--output", type=Path, help="Write to a new file instead of stdout")
    create.add_argument("--piece-size", type=int, default=DEFAULT_PIECE_SIZE, help="Bytes")
    create.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Bytes")
    verify = commands.add_parser("verify", help="Verify a file or staged batch")
    verify.add_argument("file", type=Path)
    verify.add_argument("manifest", type=Path)
    verify.add_argument("--batch", type=int, help="Zero-based batch index")
    args = parser.parse_args()

    if args.command in (None, "serve"):
        port = getattr(args, "port", 8765)
        if not 1 <= port <= 65535:
            parser.error("Port must be between 1 and 65535")
        import uvicorn

        from .app import create_app

        uvicorn.run(create_app(port), host="127.0.0.1", port=port, proxy_headers=False)
        return 0

    try:
        if args.command == "manifest":
            manifest = build_manifest(args.file, piece_size=args.piece_size, batch_size=args.batch_size)
            output = (manifest.to_json() + "\n").encode("utf-8")
            if args.output is None:
                sys.stdout.buffer.write(output)
            else:
                with args.output.open("xb") as destination:
                    destination.write(output)
            return 0
        manifest = Manifest.from_json(args.manifest.read_text(encoding="utf-8-sig"))
        verified = (verify_file(args.file, manifest) if args.batch is None
                    else verify_batch(args.file, manifest, args.batch))
        print("Verified" if verified else "Verification failed")
        return 0 if verified else 1
    except (OSError, ValueError) as exc:
        print(f"ratatoss: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
