"""Network & IP Diagnostics extension for Lumino VPN.

Demonstrates:
- `ui.settings`, tabs, groups, nested `.create()` gear submenu, checkboxes, sliders,
  comboboxes, buttons, dynamic labels, and `ui.indicator(..., progress=...)`.
- `http.get(..., via_vpn=False)` vs `http.get(..., via_vpn=True)` over Lumino SOCKS5.
- `vpn.servers()`, `vpn.ping()`, `vpn.status()`, and `@client.on("vpn_connected")`.
- `system.clipboard_set()`, `system.is_admin()`, `system.paths()`.
- `database.read/write` persistent counters and `config.export_data/import_data`.
- Console commands via `@client.on("console_input")`: `help`, `diag`, `ping`, `copy`.
"""

from __future__ import annotations

from lumino import LuminoApiError, client, config, database, events, http, system, ui, vpn

LUMINO_META = {
    "id": "lumino-net-diagnostics",
    "name": "Network & IP Diagnostics",
    "version": "1.0.0",
    "author": "Lumino",
    "description": (
        "Проверка внешнего IP напрямую и через SOCKS5 VPN, замер пинга по серверам, "
        "копирование отчёта в буфер обмена и индикатор с прогресс-баром."
    ),
    "permissions": ["vpn.read", "network", "clipboard", "notifications", "config"],
    "tags": ["network", "diagnostics", "ping", "ip", "utility"],
    "has_settings": True,
}

settings = ui.settings(
    "Диагностика сети",
    "Внешний IP (прямой и через VPN), пинг серверов, буфер обмена и отчёты",
)

diag_tab = settings.tab("Диагностика")
conn_group = diag_tab.group("Проверка подключения")
env_group = diag_tab.group("Окружение и пресеты")

auto_check_on_connect = conn_group.checkbox(
    "Автопроверка при подключении VPN",
    default=False,
    tooltip="После события vpn_connected выполнить проверку IP и пинга",
)
http_gear = auto_check_on_connect.create("Параметры HTTP-проверки")
endpoint_url = http_gear.textbox(
    "Endpoint для IP",
    default="https://api.ipify.org?format=json",
    placeholder="https://api.ipify.org?format=json",
)
timeout_sec = http_gear.slider("Таймаут запроса", 2, 15, default=5, unit="с")
copy_auto = http_gear.checkbox("Автокопирование отчёта в буфер", default=False)

ping_mode = conn_group.combo(
    "Охват замера пинга",
    "Топ-3 сервера",
    "Все серверы",
    "Только выбранный",
    default="Топ-3 сервера",
)

ip_summary = conn_group.label("Нажмите «Запустить диагностику IP и пинга»", tone="muted")
ping_summary = conn_group.label("Пинг серверов ещё не измерялся", tone="muted")

env_label = env_group.label("Окружение: ожидание загрузки...", tone="default")
counter_label = env_group.label("Выполнено проверок: 0", tone="accent")
preset_combo = env_group.combo(
    "Профиль настроек",
    "Быстрый (Топ-3)",
    "Полный (Все серверы + автокопирование)",
    default="Быстрый (Топ-3)",
)

_last_report_text = ""


def _extract_ip(resp: http.HttpResponse) -> str:
    if not resp.ok:
        return f"HTTP {resp.status}"
    try:
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("ip"):
            return str(payload["ip"]).strip()
    except Exception:
        pass
    first_line = resp.text.strip().splitlines()[0] if resp.text.strip() else ""
    return (first_line[:64] or "пустой ответ")


def _probe_ip(*, via_vpn: bool, url: str, timeout: float) -> str:
    try:
        resp = http.get(url, timeout=timeout, via_vpn=via_vpn)
        return _extract_ip(resp)
    except LuminoApiError as exc:
        if exc.code == "VPN_NOT_CONNECTED":
            return "VPN не подключён"
        return f"ошибка ({exc.code})"
    except Exception as exc:
        return f"ошибка ({type(exc).__name__})"


def _measure_pings() -> tuple[str, list[str]]:
    mode = str(ping_mode.get() or "Топ-3 сервера")
    st = vpn.status()
    selected_id = str(st.get("server_id") or vpn.selected_server() or "")
    servers = vpn.servers()

    if not servers:
        single = vpn.ping(selected_id or None)
        line = f"Выбранный сервер: {single} мс" if single >= 0 else "Серверы недоступны"
        return line, [line]

    if mode == "Только выбранный":
        targets = [s for s in servers if str(s.get("id", "")) == selected_id] or servers[:1]
    elif mode == "Топ-3 сервера":
        targets = servers[:3]
    else:
        targets = servers

    results: list[str] = []
    best_ms: int | None = None
    best_name = ""
    for srv in targets:
        sid = str(srv.get("id", ""))
        name = str(srv.get("remark") or sid or "server")
        ms = vpn.ping(sid or None)
        if ms >= 0:
            results.append(f"{name}: {ms} мс")
            if best_ms is None or ms < best_ms:
                best_ms = ms
                best_name = name
        else:
            results.append(f"{name}: таймаут")

    summary = (
        f"Лучший: {best_name} ({best_ms} мс) · проверено {len(targets)}"
        if best_ms is not None
        else f"Проверено {len(targets)}: нет отклика"
    )
    return summary, results


def _save_report(report_text: str) -> int:
    global _last_report_text
    _last_report_text = report_text
    count = int(database.read("check_count", 0) or 0) + 1
    database.write("check_count", count)
    database.write("last_report", report_text)
    counter_label.name(f"Выполнено проверок: {count}")
    return count


def _copy_last_report(*_: object) -> None:
    text = _last_report_text or "Отчёт ещё не сформирован. Запустите диагностику."
    ok = system.clipboard_set(text)
    if ok:
        client.notify("Диагностика сети", "Отчёт скопирован в буфер обмена", level="info")
    else:
        client.notify("Диагностика сети", "Не удалось записать в буфер обмена", level="warning")


def _refresh_env_info(*_: object) -> None:
    paths = system.paths()
    admin_text = "Администратор" if system.is_admin() else "Обычный пользователь"
    st = vpn.status()
    vpn_state = str(st.get("status", "Off"))
    env_label.name(
        f"Права: {admin_text} · VPN: {vpn_state} · data: {paths.get('data_dir', '-')}"
    )


def _run_ping_only(*_: object) -> None:
    ui.indicator("netdiag", "Замер пинга...", tone="accent", progress=0.45)
    summary, lines = _measure_pings()
    ping_summary.name(summary)
    count = _save_report("Пинг серверов:\n" + "\n".join(f"- {line}" for line in lines))
    ui.indicator("netdiag", summary, tone="accent", progress=1.0)
    client.log("[net-diag]", summary, f"(check #{count})")
    if bool(copy_auto.get()):
        _copy_last_report()


def _run_full_diagnostics(*_: object) -> None:
    url = str(endpoint_url.get() or "https://api.ipify.org?format=json").strip()
    timeout = float(timeout_sec.get() or 5.0)
    st = vpn.status()
    connected = bool(st.get("connected", False))

    ui.indicator("netdiag", "Проверка прямого IP...", tone="accent", progress=0.25)
    direct_ip = _probe_ip(via_vpn=False, url=url, timeout=timeout)

    ui.indicator("netdiag", "Проверка VPN IP...", tone="accent", progress=0.55)
    vpn_ip = (
        _probe_ip(via_vpn=True, url=url, timeout=timeout)
        if connected
        else "VPN отключён"
    )

    ui.indicator("netdiag", "Замер пинга серверов...", tone="accent", progress=0.80)
    ping_text, ping_lines = _measure_pings()

    ip_text = f"Прямой IP: {direct_ip} · Через VPN: {vpn_ip}"
    ip_summary.name(ip_text)
    ping_summary.name(ping_text)

    report = "\n".join(
        [
            f"VPN status: {st.get('status', 'Off')} ({st.get('server') or '—'})",
            f"Direct IP: {direct_ip}",
            f"VPN IP: {vpn_ip}",
            "Server pings:",
            *[f"  - {line}" for line in ping_lines],
        ]
    )
    count = _save_report(report)
    _refresh_env_info()

    tone = "accent" if connected else "warning"
    ui.indicator("netdiag", f"IP: {vpn_ip if connected else direct_ip} · {ping_text}", tone=tone, progress=1.0)
    client.log(f"[net-diag] #{count}: {ip_text} | {ping_text}")
    client.notify("Диагностика завершена", f"{ip_text}\n{ping_text}", level="info")
    if bool(copy_auto.get()):
        _copy_last_report()


def _apply_preset(*_: object) -> None:
    choice = str(preset_combo.get() or "")
    if choice.startswith("Полный"):
        auto_check_on_connect.set(True)
        ping_mode.set("Все серверы")
        copy_auto.set(True)
        timeout_sec.set(8)
    else:
        auto_check_on_connect.set(False)
        ping_mode.set("Топ-3 сервера")
        copy_auto.set(False)
        timeout_sec.set(5)
    config.save(choice or "default")
    exported = config.export()
    restored = config.import_data(exported)
    client.log("[net-diag] preset applied:", choice, "export_len:", len(exported), "restored_keys:", len(restored))
    client.notify("Диагностика сети", f"Применён и сохранён профиль: {choice}", level="info")


conn_group.button("Запустить диагностику IP и пинга", _run_full_diagnostics)
conn_group.button("Измерить только пинг серверов", _run_ping_only)
conn_group.button("Скопировать последний отчёт", _copy_last_report)

env_group.button("Обновить системную сводку", _refresh_env_info)
env_group.button("Применить профиль", _apply_preset)


@events.on("load")
def on_load(data: dict) -> None:
    global _last_report_text
    count = int(database.read("check_count", 0) or 0)
    _last_report_text = str(database.read("last_report", "") or "")
    counter_label.name(f"Выполнено проверок: {count}")
    _refresh_env_info()
    ui.indicator(
        "netdiag",
        f"Готово к проверке (выполнено: {count})",
        tone="muted" if count == 0 else "accent",
    )
    client.log("[net-diag] loaded, dry_run=", bool((data or {}).get("dry_run")))


@client.on("vpn_connected")
def on_vpn_connected(data: dict) -> None:
    _refresh_env_info()
    if bool((data or {}).get("dry_run")):
        return
    if bool(auto_check_on_connect.get()):
        _run_full_diagnostics()


@client.on("vpn_disconnected")
def on_vpn_disconnected(_data: dict) -> None:
    _refresh_env_info()
    ui.indicator("netdiag", "VPN отключён · нажмите для прямой проверки", tone="muted")


@client.on("console_input")
def on_console(data: dict) -> None:
    cmd = str((data or {}).get("command", "")).strip().lower()
    if cmd in ("help", "?"):
        client.log("[net-diag] Команды: diag, ping, copy, env, help")
    elif cmd == "diag":
        _run_full_diagnostics()
    elif cmd == "ping":
        _run_ping_only()
    elif cmd == "copy":
        _copy_last_report()
    elif cmd == "env":
        _refresh_env_info()
    else:
        client.log(f"[net-diag] Неизвестная команда '{cmd}'. Введите help")


@events.on("unload")
def on_unload(_data: dict) -> None:
    ui.clear_indicator("netdiag")
