"""Auto Game Tunnel — эталонное расширение на Lumino Extensions API.

Демонстрирует GameSense-стиль (`ui.new_*`, `ui.reference`, `client.set_event_callback`,
`client.delay_call`, `database`, `config`) вместе с Neverlose-механиками
(`ui.settings`, `item.create()` шестерёнка на строке, `.depends()`, `events.on`).
"""

from __future__ import annotations

from lumino import client, config, database, events, globals, split_tunnel, ui, vpn

LUMINO_META = {
    "id": "auto-game-tunnel",
    "name": "Auto Game Tunnel & Ping Guard",
    "version": "1.0.0",
    "author": "Zeermil",
    "description": "Автопереключение на самый быстрый сервер, мониторинг пинга и управление Split Tunnel.",
    "permissions": ["vpn.read", "vpn.control", "split_tunnel", "notifications", "config"],
    "tags": ["gaming", "ping", "automation"],
    "has_settings": True,
}

# Шестерёнка карточки расширения -> окно настроек
settings = ui.settings("Auto Game Tunnel", "Управление пингом и туннелем")

g_main = settings.group("Автоматизация")
guard_enabled = g_main.checkbox(
    "Следить за пингом и трафиком",
    default=bool(database.read("guard_enabled", True)),
)
max_ping = g_main.slider(
    "Порог высокого пинга",
    min_val=30,
    max_val=300,
    default=int(database.read("max_ping", 120)),
    unit="мс",
    step=5,
)
max_ping.depends(guard_enabled, True)

# Вложенная шестерёнка прямо у строки max_ping (Neverlose :create)
ping_gear = max_ping.create("Реакция на высокий пинг")
auto_switch = ping_gear.checkbox("Автоматически выбирать лучший сервер", default=False)
notify_spike = ping_gear.checkbox("Показывать уведомление при скачке пинга", default=True)
cooldown_sec = ping_gear.slider("Задержка перед переключением", 5, 60, default=15, unit="с")

# Обычный GameSense-стиль тоже работает в том же меню
target_server = ui.new_combobox("Серверы и профили", "Предпочитаемая локация", "Авто", "nl-ams-01", "de-fra-01", "fi-hel-01")
split_apps_choice = ui.new_multiselect(
    "Серверы и профили",
    "Профиль приложений",
    "Discord.exe",
    "Steam.exe",
    "Telegram.exe",
    default=["Discord.exe"],
)
accent_color = ui.new_color_picker("Серверы и профили", "Цвет индикатора", 80, 210, 140, 255)
custom_note = ui.new_string("preset_note", "default")

# Ссылка на реальный тумблер VPN внутри Lumino (аналог ui.reference / ui.find)
ref_vpn_connected = ui.reference("vpn", "connected")
ref_kill_switch = ui.reference("settings", "kill_switch")

status_lbl = ui.new_label("Действия", "Ожидание подключения VPN", tone="muted")

# Сохраняем выбор в database при любом изменении
def _save_state(_=None) -> None:
    database.write("guard_enabled", bool(ui.get(guard_enabled)))
    database.write("max_ping", int(ui.get(max_ping)))


ui.set_callback(guard_enabled, _save_state)
ui.set_callback(max_ping, _save_state)


def _apply_split_profile() -> None:
    selected = ui.get(split_apps_choice)
    split_tunnel.set_mode("exclude")
    for app in selected:
        split_tunnel.add_app(app)
    client.log(f"Split Tunnel обновлён: {len(selected)} прилож.")


ui.new_button("Действия", "Обновить список серверов", lambda: _sync_servers())
ui.new_button("Действия", "Применить профиль Split Tunnel", _apply_split_profile)
ui.new_button("Действия", "Экспортировать пресет в лог", lambda: client.log(config.export()))


def _sync_servers() -> None:
    srvs = vpn.servers()
    names = ["Авто"] + [s["id"] for s in srvs]
    ui.update(target_server, names)
    client.log(f"Доступно серверов: {len(srvs)}, VPN: {globals.vpn_state()}, KillSwitch: {ui.get(ref_kill_switch)}")


@events.on("load")
def _on_load(_ev) -> None:
    ui.indicator("guard", "Монитор готов", tone="default")
    client.delay_call(0.1, _sync_servers)


@client.on("vpn_connected")
def _on_connected(ev) -> None:
    srv = ev.get("server", "")
    ui.set(status_lbl, f"Активен: {srv} (SOCKS5 :{ev.get('socks_port', 0)})")
    ui.indicator("guard", f"Пинг: {globals.ping_ms()} мс", tone="accent")


@client.on("traffic_tick")
def _on_tick(ev) -> None:
    if not ui.get(guard_enabled):
        return
    ping = int(ev.get("ping_ms", -1))
    threshold = int(ui.get(max_ping))
    if ping > threshold and ping > 0:
        ui.indicator("guard", f"Высокий пинг {ping} мс!", tone="danger")
        if ui.get(notify_spike):
            client.notify("Ping Guard", f"Задержка {ping} мс превысила порог {threshold} мс", level="warning")
    elif ping >= 0:
        ui.indicator("guard", f"OK · {ping} мс", tone="accent")


@events.on("vpn_disconnected")
def _on_disconnected(_ev) -> None:
    ui.set(status_lbl, "VPN отключён")
    ui.indicator("guard", "Ожидание", tone="muted")
