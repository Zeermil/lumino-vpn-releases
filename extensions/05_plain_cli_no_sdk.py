"""Тест 05: Обычный Python-скрипт с argparse БЕЗ импорта `lumino` (автогенерация fallback-UI)."""

from __future__ import annotations

import argparse
import json
import platform
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Обычный standalone-скрипт без SDK lumino для проверки авто-UI."
    )
    parser.add_argument(
        "--mode",
        choices=("fast", "deep", "audit"),
        default="fast",
        help="Режим диагностики окружения",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не вносить изменений (только отчёт)",
    )
    parser.add_argument(
        "--tag",
        default="lumino-smoke",
        help="Текстовая метка запуска",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    report = {
        "mode": args.mode,
        "dry_run": args.dry_run,
        "tag": args.tag,
        "python": platform.python_version(),
        "system": f"{platform.system()} {platform.release()}",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
