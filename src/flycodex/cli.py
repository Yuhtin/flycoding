"""Explicit local commands; only `run` can spend pilot reservations."""
import argparse
import json
from pathlib import Path
import sys

from .storage import load_json


def main(argv=None):
    parser = argparse.ArgumentParser(prog="flycodex", description="Piloto local de controle neural do Codex")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("prepare", "Baixar e verificar o dataset fixado"),
        ("probe", "Verificar mecanismos neurais, sem Codex"),
        ("run", "Executar ou retomar o piloto de até 30 instruções"),
        ("status", "Ler o estado público do piloto"),
        ("serve", "Abrir o observatório HTTP local, somente leitura"),
        ("report", "Exportar relatório local sem eventos brutos"),
    ):
        command = commands.add_parser(name, help=help_text)
        if name in {"prepare", "probe", "run"}:
            command.add_argument("--data-dir", type=Path, default=Path("data"))
        if name in {"run", "status", "serve", "report"}:
            command.add_argument("--run-dir", type=Path, default=Path("runs/pilot"))
        if name == "run":
            command.add_argument("--model", default="gpt-6-astra", help="Modelo fixado antes do primeiro envio (padrão: gpt-6-astra)")
            command.add_argument("--stop-after-attempts", type=int, choices=range(1, 7), help="Parar em um limite seguro de tentativas nesta execução")
        if name in {"probe", "report"}:
            command.add_argument("--output-dir", type=Path, default=Path("runs/probe" if name == "probe" else "docs/results"))
        if name == "serve":
            command.add_argument("--port", type=int, default=8765)
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
            result = Pilot(args.run_dir, args.data_dir, model=args.model).run(stop_after_attempts=args.stop_after_attempts)
        elif args.command == "status":
            result = load_json(args.run_dir / "public/snapshot.json")
        elif args.command == "report":
            from .pilot import write_report
            result = write_report(args.run_dir, args.output_dir)
        else:
            from .web import create_server
            server = create_server(args.run_dir, port=args.port)
            print(f"Observatório: http://127.0.0.1:{server.server_port} (somente leitura)", flush=True)
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
        print("Interrompido. A reserva permanece consumida; retome pelo mesmo diretório.", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"flycodex: {exc}", file=sys.stderr)
        return 1
