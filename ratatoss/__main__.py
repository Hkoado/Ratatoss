"""Run the local node, or work with manifests on the command line."""

import argparse
import sqlite3
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
from .settings import LOOPBACK, NodeSettings, controller_database, node_data_dir


def main() -> int:
    parser = argparse.ArgumentParser(prog="ratatoss")
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Run the loopback UI")
    serve.add_argument("--port", type=int)
    serve.add_argument("--data-dir", type=Path)
    init = commands.add_parser("init", help="Initialize a local SQLite database")
    roles = init.add_subparsers(dest="role", required=True)
    node = roles.add_parser("node", help="Initialize the Node database")
    node.add_argument("--data-dir", type=Path)
    controller = roles.add_parser("controller", help="Initialize the controller database")
    controller.add_argument("--db", type=Path)
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

    try:
        if args.command in (None, "serve", "init"):
            from .database import NODE_DATABASE_NAME, initialize_database

            if args.command == "init":
                path = (node_data_dir(args.data_dir) / NODE_DATABASE_NAME if args.role == "node"
                        else controller_database(args.db))
                initialize_database(path, args.role)
                print(f"Initialized {args.role} database")
                return 0

            settings = NodeSettings.load(getattr(args, "port", None), getattr(args, "data_dir", None))
            initialize_database(settings.data_dir / NODE_DATABASE_NAME, "node")

            import uvicorn

            from .app import create_app

            uvicorn.run(create_app(settings.port), host=LOOPBACK, port=settings.port, proxy_headers=False)
            return 0

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
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"ratatoss: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
