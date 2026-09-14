"""Explicit local commands; only `run` can spend pilot reservations."""
import argparse
import json
from pathlib import Path
import sys

from .storage import load_json


def main(argv=None):
    parser = argparse.ArgumentParser(prog="flycodex", description="Local neural control pilot for Codex")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("prepare", "Download and verify the pinned dataset"),
        ("probe", "Verify neural mechanisms without Codex"),
        ("run", "Run or resume the pilot of up to 30 instructions"),
        ("status", "Read the public pilot state"),
        ("serve", "Open the local read-only HTTP observatory"),
        ("report", "Export a local report without raw events"),
    ):
        command = commands.add_parser(name, help=help_text)
        if name in {"prepare", "probe", "run"}:
            command.add_argument("--data-dir", type=Path, default=Path("data"))
        if name in {"run", "status", "serve", "report"}:
            command.add_argument("--run-dir", type=Path, default=Path("runs/pilot"))
        if name == "run":
            command.add_argument("--backend", choices=("codex", "opencode"), default="codex")
            command.add_argument("--model", help="Model fixed before the first submission")
            command.add_argument("--max-calls", type=int, help="Durable total submission cap")
            command.add_argument("--stop-after-attempts", type=int, choices=range(1, 7), help="Stop at a safe attempt boundary in this run")
        if name in {"probe", "report"}:
            command.add_argument("--output-dir", type=Path, default=Path("runs/probe" if name == "probe" else "docs/results"))
        if name == "serve":
            command.add_argument("--data-dir", type=Path, default=Path("data"),
                                 help="Prepared neural data for --lab")
            command.add_argument("--port", type=int, default=8765)
            command.add_argument("--lab", action="store_true",
                                 help="Enable the local neural lab controls")
            command.add_argument("--demo", action="store_true", help="View the bundled genuine pilot; no run directory or Codex required")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            from .neural import prepare_data
            result = prepare_data(args.data_dir)
        elif args.command == "probe":
            from .neural import probe
            from .pilot import verify_data
            verify_data(args.data_dir)
            result = probe(args.data_dir, args.output_dir)
        elif args.command == "run":
            from .pilot import Pilot
            from .opencode import DEFAULT_MODEL
            model = args.model or (DEFAULT_MODEL if args.backend == "opencode" else "gpt-6-astra")
            result = Pilot(
                args.run_dir,
                args.data_dir,
                model=model,
                backend=args.backend,
                max_calls=args.max_calls,
            ).run(stop_after_attempts=args.stop_after_attempts)
        elif args.command == "status":
            result = load_json(args.run_dir / "public/snapshot.json")
        elif args.command == "report":
            from .pilot import write_report
            result = write_report(args.run_dir, args.output_dir)
        else:
            from .web import create_server
            if args.demo and args.lab:
                raise ValueError("--demo and --lab are mutually exclusive")
            server = create_server(args.run_dir, port=args.port, demo=args.demo,
                                   lab=args.lab, data_dir=args.data_dir)
            mode = "lab" if args.lab else ("demo archive · read-only" if args.demo else "read-only")
            print(f"Observatory: http://127.0.0.1:{server.server_port} ({mode})", flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
            return 0
        if args.command in {"run", "status"}:
            print(json.dumps({key: result[key] for key in ("evidence", "status", "budget", "active_attempt", "error") if key in result}, indent=2))
        else:
            print(json.dumps(result, indent=2))
        return 1 if result.get("status") == "recovery_error" else 0
    except KeyboardInterrupt:
        print("Interrupted. Any reservation remains consumed; resume from the same directory.", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"flycodex: {exc}", file=sys.stderr)
        return 1
