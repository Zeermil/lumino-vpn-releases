"""Тест 03: События VPN, управление Split Tunneling, SOCKS5 HTTP и команды в консоли."""

LUMINO_META = {
    "id": "test-03-vpn-split-http",
    "name": "Тест 03 — VPN, Split Tunnel & SOCKS5",
    "description": "Реагирует на события подключения VPN, добавляет приложения в Split Tunnel и проверяет IP через SOCKS5.",
    "version": "1.0.0",
    "author": "Lumino QA",
    "permissions": ["vpn.read", "vpn.control", "split_tunnel", "network", "notifications"],
    "has_settings": True,
}

from lumino import client, database, events, globals, http, split_tunnel, ui, vpn

settings = ui.settings("VPN & Split Tunnel Monitor", "Авто-правила при подключении VPN")
grp_split = settings.tab("Split Tunnel").group("Автоматическое добавление")

auto_manage_cb = grp_split.checkbox(
    "Добавлять выбранное приложение при подключении VPN",
    default=bool(database.read("auto_manage", False)),
)
app_name_txt = grp_split.textbox(
    "Имя процесса (.exe)",
    default=str(database.read("app_name", "notepad.exe")),
    placeholder="например steam.exe",
)
split_status_lbl = grp_split.label("Split Tunnel: неизвестно", tone="muted")

grp_net = settings.tab("Сеть").group("Пинг и внешний IP")
net_status_lbl = grp_net.label("Нажмите кнопку для проверки пинга/IP", tone="muted")


def _refresh_split_state() -> None:
    st = split_tunnel.state()
    mode = st.get("mode", "off")
    apps = st.get("apps", [])
    split_status_lbl.set(f"Режим: {mode} · Приложений в списке: {len(apps)}")
    ui.indicator("split", f"Split: {mode} ({len(apps)})")


def _add_app_now() -> None:
    name = str(app_name_txt.get()).strip()
    if not name:
        client.error_log("Укажите имя процесса (.exe)")
        return
    apps = split_tunnel.add_app(name)
    _refresh_split_state()
    client.color_log(120, 230, 140, f"Добавлено '{name}'. Всего в Split Tunnel: {len(apps)}")


def _remove_app_now() -> None:
    name = str(app_name_txt.get()).strip()
    if not name:
        return
    apps = split_tunnel.remove_app(name)
    _refresh_split_state()
    client.log(f"Удалено '{name}'. Осталось: {len(apps)}")


def _ping_selected() -> None:
    ms = vpn.ping()
    srv = globals.selected_server() or "не выбран"
    msg = f"Пинг до {srv}: {ms} мс" if ms >= 0 else f"Не удалось измерить пинг ({srv})"
    net_status_lbl.set(msg)
    client.log(msg)


def _check_public_ip() -> None:
    try:
        resp = http.get("https://api.ipify.org?format=json", via_vpn="auto", timeout=8.0)
        msg = f"HTTP {resp.status}: {resp.text.strip()}"
        net_status_lbl.set(msg)
        client.color_log(140, 220, 255, msg)
    except Exception as exc:
        net_status_lbl.set(f"Ошибка запроса: {exc}")
        client.error_log(f"HTTP check failed: {exc}")


auto_manage_cb.callback(lambda it: database.write("auto_manage", bool(it.get())))
app_name_txt.callback(lambda it: database.write("app_name", str(it.get())))

grp_split.button("Добавить приложение в Split Tunnel", _add_app_now)
grp_split.button("Убрать приложение из Split Tunnel", _remove_app_now)
grp_net.button("Измерить пинг выбранного сервера", _ping_selected)
grp_net.button("Проверить внешний IP (via_vpn=auto)", _check_public_ip)


@events.on("load")
def _on_load(_ev) -> None:
    _refresh_split_state()
    client.log("03_vpn_events_and_split_tunnel загружен. Команды консоли: status, apps, ping, checkip")


@events.on("vpn_connected")
def _on_vpn_connect(ev) -> None:
    server = ev.get("server") or globals.active_server()
    client.color_log(120, 230, 140, f"Событие vpn_connected -> сервер={server}, socks={globals.socks_port()}")
    if auto_manage_cb.get():
        _add_app_now()
    client.notify("Split Monitor", f"VPN подключён: {server}", level="success")


@events.on("vpn_disconnected")
def _on_vpn_disconnect(_ev) -> None:
    client.log("Событие vpn_disconnected: туннель остановлен.")


@client.on("console_input")
def _on_console(cmd: str) -> bool:
    c = cmd.strip().lower()
    if c == "help":
        client.log("Доступные команды: status, apps, ping, checkip")
        return True
    if c == "status":
        client.log(f"vpn.status() = {vpn.status()}")
        return True
    if c == "apps":
        client.log(f"split_tunnel.state() = {split_tunnel.state()}")
        return True
    if c == "ping":
        _ping_selected()
        return True
    if c == "checkip":
        _check_public_ip()
        return True
    return False
