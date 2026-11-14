#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity: «Вход в аккаунт из-под санкций» (Lumino VPN Extension + CLI).

Работает в двух режимах:
1. Внутри Lumino VPN (вкладка «Дополнения»): рисует живое окно настроек по шестерёнке,
   показывает статус бинарников, позволяет применить/откатить патч в 1 клик,
   сохраняет настройки в database и при подключении VPN может добавлять Antigravity
   в Split Tunneling.
2. Как обычная консольная CLI-утилита:
     python antigravity_signin_unlock.py --check
     python antigravity_signin_unlock.py
     python antigravity_signin_unlock.py --revert
     python antigravity_signin_unlock.py --self-test
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

LUMINO_META = {
    "id": "antigravity-unlock",
    "name": "Antigravity Sign-In Unlock",
    "version": "1.1.0",
    "author": "Zeermil",
    "description": "Патч eligibility-проверки (ineligible -> inexigible) в language_server/agy и автодобавление в Split Tunnel.",
    "permissions": ["fs", "process", "registry", "split_tunnel", "notifications"],
    "tags": ["antigravity", "patch", "split-tunnel"],
    "has_settings": True,
}

# --------------------------------------------------------------------------
# Ядро патча (10 байт -> 10 байт, размер и структура PE/Mach-O/ELF не меняются)
# --------------------------------------------------------------------------

FROM = b"ineligible"
TO = b"inexigible"
assert len(FROM) == len(TO) == 10, "патч обязан быть одинаковой длины"

TEMP_SUFFIX = ".agtmp"
BACKUP_SUFFIX = ".agbak"

PATCHED = "patched"
UNPATCHED = "unpatched"
MIXED = "mixed"
MISSING = "missing"
UNREADABLE = "unreadable"

STATE_RU = {
    PATCHED: "уже пропатчен",
    UNPATCHED: "не пропатчен",
    MIXED: "смешанное состояние",
    MISSING: "сигнатура не найдена",
    UNREADABLE: "не читается",
}


@dataclass
class Target:
    path: Path
    state: str = MISSING
    from_count: int = 0
    to_count: int = 0
    size: int = 0
    error: str | None = None

    @property
    def occurrences(self) -> int:
        return self.from_count + self.to_count


@dataclass
class Install:
    root: Path
    targets: list[Target] = field(default_factory=list)


def human_size(n: float) -> str:
    for unit in ("Б", "КиБ", "МиБ", "ГиБ"):
        if n < 1024 or unit == "ГиБ":
            return f"{n:.1f} {unit}" if unit != "Б" else f"{int(n)} {unit}"
        n /= 1024.0
    return f"{n:.1f} ГиБ"


def scan_file(path: Path) -> Target:
    t = Target(path=path)
    try:
        t.size = path.stat().st_size
        tail = b""
        with path.open("rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                buf = tail + chunk
                t.from_count += buf.count(FROM)
                t.to_count += buf.count(TO)
                tail = buf[-(len(FROM) - 1) :]
    except OSError as e:
        t.state = UNREADABLE
        t.error = str(e)
        return t

    if t.to_count and not t.from_count:
        t.state = PATCHED
    elif t.from_count and not t.to_count:
        t.state = UNPATCHED
    elif t.from_count and t.to_count:
        t.state = MIXED
    else:
        t.state = MISSING
    return t


def find_offsets(path: Path, needle: bytes) -> list[int]:
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size < len(needle):
        return []
    out: list[int] = []
    try:
        with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            i = 0
            while True:
                j = mm.find(needle, i)
                if j < 0:
                    return out
                out.append(j)
                i = j + len(needle)
    except (OSError, ValueError):
        return out


def kill_holders(path: Path, close_app: bool = False) -> None:
    if os.name == "nt":
        names = ["language_server.exe", "language_server_windows_x64.exe", "agy.exe"]
        if close_app:
            names += ["Antigravity.exe", "Antigravity IDE.exe", "Antigravity CLI.exe"]
        for name in names:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", name],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                    timeout=15,
                )
            except (OSError, subprocess.SubprocessError):
                pass
    else:
        patterns = ["language_server", "/agy"]
        if close_app:
            patterns += ["antigravity", "Antigravity"]
        for pat in patterns:
            try:
                subprocess.run(
                    ["pkill", "-f", pat],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=15,
                )
            except (OSError, subprocess.SubprocessError):
                pass


def patch_target(
    target: Target,
    reverse: bool = False,
    kill: bool = False,
    close_app: bool = False,
    backup: bool = False,
) -> int:
    frm, to = (TO, FROM) if reverse else (FROM, TO)
    try:
        offsets = find_offsets(target.path, frm)
    except OSError as e:
        raise RuntimeError(f"не прочитать: {e}") from e
    if not offsets:
        return 0

    before_size = target.path.stat().st_size

    if backup and not reverse:
        bak = target.path.with_name(target.path.name + BACKUP_SUFFIX)
        if not bak.exists():
            try:
                shutil.copy2(target.path, bak)
            except OSError as e:
                print(f"        [предупреждение] бэкап не создан: {e}", file=sys.stderr)

    tmp = target.path.with_name(f"{target.path.name}.{os.getpid()}{TEMP_SUFFIX}")
    attempts = 3
    for attempt in range(attempts):
        try:
            shutil.copyfile(target.path, tmp)
            with open(tmp, "r+b") as f:
                for off in offsets:
                    f.seek(off)
                    f.write(to)
                f.flush()
                os.fsync(f.fileno())
            if os.name != "nt":
                shutil.copymode(target.path, tmp)
            os.replace(tmp, target.path)
            break
        except OSError as e:
            try:
                tmp.unlink()
            except OSError:
                pass
            locked = isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32, 33)
            if locked and attempt == 0 and (kill or close_app):
                kill_holders(target.path, close_app)
                time.sleep(1.0)
                continue
            if locked and attempt < attempts - 1:
                time.sleep(0.4)
                continue
            raise

    after = target.path.stat().st_size
    if after != before_size:
        raise RuntimeError(f"размер изменился после записи: {before_size} -> {after}")
    check = scan_file(target.path)
    if reverse and check.from_count == 0:
        raise RuntimeError("после отката не найдено ни одного `ineligible`")
    if not reverse and check.to_count == 0:
        raise RuntimeError("после патча не найдено ни одного `inexigible`")
    return len(offsets)


def is_snap(path: Path) -> bool:
    return str(path).startswith("/snap") or str(path).startswith("/var/lib/snapd")


def resources_dir(root: Path) -> Path:
    mac = root / "Contents" / "Resources"
    return mac if mac.is_dir() else root / "resources"


def is_binary_name(name: str) -> bool:
    lower = name.lower()
    if lower.endswith(TEMP_SUFFIX) or lower.endswith(BACKUP_SUFFIX):
        return False
    return lower.startswith("language_server") or lower in ("agy", "agy.exe")


def is_install_root(p: Path) -> bool:
    try:
        if not p.is_dir():
            return False
    except OSError:
        return False
    res = p / "resources"
    try:
        if res.is_dir() and any((res / n).exists() for n in ("app.asar", "app", "bin")):
            return True
    except OSError:
        pass
    if (p / "agy.exe").is_file() or (p / "agy").is_file():
        return True
    if os.name == "nt":
        if any((p / n).is_file() for n in ("Antigravity.exe", "Antigravity IDE.exe", "antigravity.exe")):
            return True
    else:
        if any((p / n).is_file() for n in ("antigravity", "Antigravity", "antigravity-ide")):
            return True
    if (p / "out" / "main.js").exists() or (p / "dist" / "main.js").exists():
        return True
    if (p / "Contents" / "Resources").is_dir():
        return True
    try:
        for e in p.iterdir():
            if e.is_file() and is_binary_name(e.name):
                return True
    except OSError:
        pass
    return False


def resolve_install_root(raw: Path) -> Path | None:
    p = raw.expanduser()
    try:
        if p.is_file():
            p = p.parent
        if not p.exists():
            return None
        if is_install_root(p):
            return p
        cur = p
        for _ in range(4):
            if cur.parent == cur:
                break
            cur = cur.parent
            if is_install_root(cur):
                return cur
        for sub in ("Antigravity IDE", "Antigravity", "agy", "resources", "Contents"):
            cand = p / sub
            if is_install_root(cand):
                return cand
    except OSError:
        return None
    return None


def _registry_roots() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    out: list[Path] = []
    views = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, sub in views:
        try:
            with winreg.OpenKey(hive, sub) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, i)) as key:
                            def q(name: str) -> str:
                                try:
                                    return str(winreg.QueryValueEx(key, name)[0])
                                except OSError:
                                    return ""
                            disp = q("DisplayName")
                            loc = q("InstallLocation")
                    except OSError:
                        continue
                    d = disp.lower()
                    if loc and ("antigravity" in d or d.startswith("agy") or " agy" in d):
                        out.append(Path(loc))
        except OSError:
            continue
    return out


def _candidate_roots() -> list[Path]:
    cands: list[Path] = []
    home = Path.home()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
        pf = Path(os.environ.get("PROGRAMFILES", "")) if os.environ.get("PROGRAMFILES") else None
        pf86 = Path(os.environ.get("PROGRAMFILES(X86)", "")) if os.environ.get("PROGRAMFILES(X86)") else None
        for base in (local, pf, pf86):
            if not base:
                continue
            for name in ("Antigravity", "Antigravity IDE"):
                cands.append(base / name)
            cands.append(base / "Programs" / "Antigravity")
            cands.append(base / "Programs" / "Antigravity IDE")
        if local:
            cands += [local / "agy" / "bin", local / "agy"]
        cands.append(home / ".gemini" / "bin")
    else:
        for base in ("/opt", "/usr/share", "/usr/lib", "/usr/local/share"):
            for name in ("Antigravity", "Antigravity IDE", "antigravity", "antigravity-ide"):
                cands.append(Path(base) / name)
        cands += [
            home / ".local" / "share" / "Antigravity",
            home / ".local" / "share" / "Antigravity IDE",
            home / "Antigravity",
            home / "Antigravity IDE",
            home / ".local" / "bin",
            home / ".agy" / "bin",
            home / ".agy",
            home / ".local" / "share" / "agy" / "bin",
            home / ".gemini" / "bin",
        ]
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if d:
                cands.append(Path(d))
    cands += _registry_roots()
    return cands


def find_installs(extra_paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()

    def add(root: Path) -> None:
        try:
            key = os.path.normcase(os.path.realpath(str(root)))
        except OSError:
            key = os.path.normcase(str(root))
        if key in seen:
            return
        seen.add(key)
        found.append(root)

    if extra_paths:
        for raw in extra_paths:
            try:
                if raw.is_file():
                    add(raw)
                    continue
            except OSError:
                pass
            resolved = resolve_install_root(raw)
            if resolved:
                add(resolved)
        return found

    for cand in _candidate_roots():
        if os.name != "nt" and is_snap(cand):
            continue
        resolved = resolve_install_root(cand)
        if resolved:
            add(resolved)
    return found


def binary_targets(root: Path) -> list[Path]:
    if root.is_file():
        return [root]

    res = resources_dir(root)
    dirs = [root, res / "bin", res / "app" / "extensions" / "antigravity" / "bin"]
    if (res / "app" / "extensions" / "agy").is_dir():
        dirs.append(Path.home() / ".gemini" / "bin")

    cands: list[Path] = []
    for d in dirs:
        try:
            if not d.is_dir():
                continue
            for e in d.iterdir():
                if e.is_file() and is_binary_name(e.name):
                    cands.append(e)
        except OSError:
            continue

    out: list[Path] = []
    seen: set[str] = set()
    for p in cands:
        try:
            if os.name != "nt" and is_snap(p):
                continue
            real = Path(os.path.realpath(p))
            key = os.path.normcase(str(real))
            if key in seen:
                continue
            seen.add(key)
            out.append(real)
        except OSError:
            continue
    return out


class Paint:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _c(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.enabled else s

    def green(self, s: str) -> str: return self._c("32", s)
    def yellow(self, s: str) -> str: return self._c("33", s)
    def red(self, s: str) -> str: return self._c("31", s)
    def dim(self, s: str) -> str: return self._c("2", s)
    def bold(self, s: str) -> str: return self._c("1", s)


def collect(roots: list[Path]) -> list[Install]:
    installs: list[Install] = []
    for root in roots:
        inst = Install(root=root)
        for p in binary_targets(root):
            inst.targets.append(scan_file(p))
        installs.append(inst)
    return installs


def run_self_test() -> tuple[bool, str]:
    payload = FROM + FROM + b"_tiers" + b"middle" + FROM + b"tail" + FROM
    expected_patched = payload.replace(FROM, TO)
    with tempfile.TemporaryDirectory(prefix="ag_unlock_selftest_") as td:
        p = Path(td) / "language_server_test.bin"
        p.write_bytes(payload)
        t = scan_file(p)
        assert t.state == UNPATCHED and t.from_count == 4, t
        assert find_offsets(p, FROM) == [0, 10, 32, len(payload) - 10]

        n = patch_target(t)
        assert n == 4
        assert p.stat().st_size == len(payload)
        assert p.read_bytes() == expected_patched

        t = scan_file(p)
        assert t.state == PATCHED and t.to_count == 4

        n = patch_target(t, reverse=True)
        assert n == 4
        assert p.read_bytes() == payload

        t = scan_file(p)
        assert patch_target(t) == 4
        t = scan_file(p)
        assert patch_target(t) == 0 and t.state == PATCHED
        t = scan_file(p)
        assert patch_target(t, reverse=True) == 4
        t = scan_file(p)
        assert patch_target(t, reverse=True) == 0 and t.state == UNPATCHED
    return True, "Самопроверка пройдена: патч, размер, откат и идемпотентность — ok."


def to_json(installs: list[Install]) -> str:
    data = []
    for inst in installs:
        data.append(
            {
                "root": str(inst.root),
                "targets": [
                    {
                        "path": str(t.path),
                        "state": t.state,
                        "size": t.size,
                        "ineligible": t.from_count,
                        "inexigible": t.to_count,
                        "error": t.error,
                    }
                    for t in inst.targets
                ],
            }
        )
    return json.dumps(data, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Lumino VPN Extensions UI + Events integration
# --------------------------------------------------------------------------

def _setup_lumino_extension() -> None:
    from lumino import client, database, events, split_tunnel, ui

    # Иконка шестерёнки на карточке расширения в списке «Дополнения»
    settings = ui.settings("Antigravity Sign-In Unlock", "Разблокировка входа и туннелирование")

    tab_main = settings.tab("Патчер")
    tab_vpn = settings.tab("Сеть и VPN")

    g_paths = tab_main.group("Поиск установок")
    auto_find = g_paths.checkbox(
        "Автопоиск установок Antigravity",
        default=bool(database.read("auto_find", True)),
        tooltip="Ищет в AppData, Program Files, PATH и реестре Uninstall",
    )
    custom_path = g_paths.textbox(
        "Путь к папке или бинарнику",
        default=str(database.read("custom_path", "")),
        placeholder=r"C:\Users\...\Programs\Antigravity",
    ).depends(auto_find, False)

    g_opts = tab_main.group("Режим патча")
    backup_cb = g_opts.checkbox(
        "Создавать резервную копию (.agbak)",
        default=bool(database.read("backup", True)),
    )
    kill_cb = g_opts.checkbox(
        "Закрывать language_server / agy, если файл занят",
        default=bool(database.read("kill", True)),
    )
    # Вложенная шестерёнка на элементе kill_cb (паттерн Neverlose `item.create()`)
    kill_gear = kill_cb.create("Детали завершения процессов")
    close_app_cb = kill_gear.checkbox(
        "Закрывать и оболочку Antigravity.exe (осторожно с несохранёнными вкладками)",
        default=bool(database.read("close_app", False)),
    )

    g_actions = tab_main.group("Состояние и управление")
    status_lbl = g_actions.label("Статус: не проверялся", tone="muted")
    targets_list = g_actions.listbox("Найденные целевые файлы", height=4)

    g_net = tab_vpn.group("Связка с Lumino VPN")
    add_split_cb = g_net.checkbox(
        "Автодобавление Antigravity / agy в Split Tunnel при запуске VPN",
        default=bool(database.read("add_split", False)),
    )
    auto_on_vpn_cb = g_net.checkbox(
        "Проверять и применять патч автоматически при подключении VPN",
        default=bool(database.read("auto_on_vpn", False)),
    )

    def persist_prefs(_=None) -> None:
        database.write("auto_find", bool(ui.get(auto_find)))
        database.write("custom_path", str(ui.get(custom_path)))
        database.write("backup", bool(ui.get(backup_cb)))
        database.write("kill", bool(ui.get(kill_cb)))
        database.write("close_app", bool(ui.get(close_app_cb)))
        database.write("add_split", bool(ui.get(add_split_cb)))
        database.write("auto_on_vpn", bool(ui.get(auto_on_vpn_cb)))

    for item in (auto_find, custom_path, backup_cb, kill_cb, close_app_cb, add_split_cb, auto_on_vpn_cb):
        ui.set_callback(item, persist_prefs)

    def resolve_installs() -> list[Install]:
        extra = []
        if not ui.get(auto_find):
            raw = str(ui.get(custom_path)).strip()
            if raw:
                extra.append(Path(raw))
        roots = find_installs(extra)
        return collect(roots) if roots else []

    def refresh_status(quiet: bool = False) -> list[Install]:
        installs = resolve_installs()
        targets = [t for inst in installs for t in inst.targets]
        lines = [f"[{STATE_RU[t.state]}] {t.path.name} ({human_size(t.size)})" for t in targets]
        ui.update(targets_list, lines if lines else ["(бинарники не найдены)"])

        if not targets:
            ui.set(status_lbl, "Установки Antigravity не найдены")
            ui.indicator("patch", "Не найдено", tone="muted")
            if not quiet:
                client.log("Установки Antigravity не найдены.")
            return installs

        patched_n = sum(1 for t in targets if t.state == PATCHED)
        unpatched_n = sum(1 for t in targets if t.state in (UNPATCHED, MIXED))
        summary = f"Пропатчено: {patched_n}/{len(targets)} · Ожидает: {unpatched_n}"
        ui.set(status_lbl, summary)
        tone = "accent" if unpatched_n == 0 and patched_n > 0 else "default"
        ui.indicator("patch", f"Патч: {patched_n}/{len(targets)}", tone=tone)
        if not quiet:
            client.log(summary)
        return installs

    def apply_patch(reverse: bool = False) -> None:
        installs = resolve_installs()
        targets = [t for inst in installs for t in inst.targets]
        if not targets:
            client.error_log("Целевые бинарники Antigravity не найдены.")
            refresh_status(quiet=True)
            return
        changed = 0
        errors = 0
        for t in targets:
            if t.state in (MISSING, UNREADABLE):
                continue
            try:
                n = patch_target(
                    t,
                    reverse=reverse,
                    kill=bool(ui.get(kill_cb)),
                    close_app=bool(ui.get(close_app_cb)),
                    backup=bool(ui.get(backup_cb)),
                )
                if n > 0:
                    changed += 1
                    verb = "Откат" if reverse else "Патч"
                    client.color_log(120, 230, 140, f"{verb} {t.path.name}: {n} замен, размер не изменён")
            except Exception as exc:
                errors += 1
                client.error_log(f"Ошибка {t.path.name}: {exc}")
        refresh_status(quiet=True)
        if errors == 0 and changed > 0:
            client.notify(
                "Antigravity Unlock",
                f"{'Откат' if reverse else 'Патч'} выполнен ({changed} файл(ов))",
                level="success",
            )

    def ensure_split_tunnel() -> None:
        for exe in ("Antigravity.exe", "language_server.exe", "language_server_windows_x64.exe", "agy.exe"):
            split_tunnel.add_app(exe)
        client.log("Antigravity добавлен в список Split Tunneling")

    g_actions.button("Проверить статус", lambda: refresh_status(quiet=False))
    g_actions.button("Применить патч", lambda: apply_patch(reverse=False))
    g_actions.button("Откатить патч", lambda: apply_patch(reverse=True))
    g_actions.button("Самопроверка логики", lambda: client.color_log(120, 230, 140, run_self_test()[1]))
    g_net.button("Добавить в Split Tunnel сейчас", ensure_split_tunnel)

    @events.on("load")
    def _on_load(_ev) -> None:
        refresh_status(quiet=True)

    @events.on("vpn_connected")
    def _on_vpn_connected(ev) -> None:
        if ui.get(add_split_cb):
            ensure_split_tunnel()
        if ui.get(auto_on_vpn_cb):
            client.log(f"VPN подключён ({ev.get('server', '')}), проверяем патч Antigravity...")
            apply_patch(reverse=False)

    @client.on("console_input")
    def _on_console(cmd: str) -> bool:
        c = cmd.strip().lower()
        if c == "check":
            refresh_status(quiet=False)
            return True
        if c == "patch":
            apply_patch(reverse=False)
            return True
        if c == "revert":
            apply_patch(reverse=True)
            return True
        if c in ("self-test", "selftest"):
            client.color_log(120, 230, 140, run_self_test()[1])
            return True
        return False


if __name__ == "__lumino_extension__":
    _setup_lumino_extension()


# --------------------------------------------------------------------------
# Standalone CLI mode
# --------------------------------------------------------------------------

def cli_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="antigravity_signin_unlock.py")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", "--dry-run", action="store_true", dest="check")
    mode.add_argument("--revert", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--kill", action="store_true")
    ap.add_argument("--close-app", action="store_true")
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    if args.json and args.revert:
        ap.error("--json несовместим с --revert")
    if args.json:
        args.check = True

    paint = Paint(enabled=(not args.no_color) and sys.stdout.isatty())
    if args.self_test:
        _, msg = run_self_test()
        print(paint.green(msg))
        return 0

    roots = find_installs([Path(p) for p in args.path])
    if not roots:
        print(paint.red("Установки Antigravity не найдены."), file=sys.stderr)
        return 2

    installs = collect(roots)
    if args.json:
        print(to_json(installs))
        return 0

    for inst in installs:
        print(paint.bold(str(inst.root)))
        for t in inst.targets:
            print(f"  [{STATE_RU[t.state]}] {t.path.name} ({human_size(t.size)}, ineligible={t.from_count}, inexigible={t.to_count})")

    if args.check:
        return 0

    errors = 0
    for inst in installs:
        for t in inst.targets:
            if t.state in (MISSING, UNREADABLE):
                continue
            try:
                n = patch_target(t, reverse=args.revert, kill=args.kill, close_app=args.close_app, backup=args.backup)
                if n > 0:
                    print(paint.green(f"  {t.path.name}: {n} замен ok"))
            except Exception as exc:
                print(paint.red(f"  {t.path.name}: {exc}"), file=sys.stderr)
                errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
