"""Тест 01: Полная витрина всех 10 типов UI-контролов GameSense/Lumino API, индикаторов и пресетов."""

LUMINO_META = {
    "id": "test-01-ui-showcase",
    "name": "Тест 01 — Все UI контролы",
    "description": "Проверяет checkbox, slider, combo, multiselect, textbox, listbox, button, label, hotkey, color и presets.",
    "version": "1.0.0",
    "author": "Lumino QA",
    "permissions": ["vpn.read", "config", "hotkeys", "notifications"],
    "has_settings": True,
}

from lumino import client, config, database, events, globals, ui

# Значок шестерёнки появляется автоматически благодаря ui.new_* / ui.settings
ui.settings("Витрина UI-контролов", "Все 10 видов виджетов + индикаторы + config")

# 1. Checkbox + Tooltip
cb_enabled = ui.new_checkbox(
    "Основные контролы",
    "Включить тестовый профиль",
    default=bool(database.read("enabled", True)),
    tab_name="Основные",
).tooltip("Управляет активностью тестового профиля")

# 2. Slider (с scale, unit и named tooltips)
sl_delay = ui.new_slider(
    "Основные контролы",
    "Таймаут проверки",
    min_val=100,
    max_val=5000,
    default=int(database.read("timeout_ms", 1200)),
    unit=" мс",
    step=50,
    tooltips={100: "Мин", 1200: "Стандарт", 5000: "Макс"},
    tab_name="Основные",
)

# 3. Combobox
cmb_proto = ui.new_combobox(
    "Основные контролы",
    "Режим маршрута",
    "Авто (VLESS)",
    "Только TUN",
    "Локальный SOCKS5",
    default=str(database.read("route_mode", "Авто (VLESS)")),
    tab_name="Основные",
)

# 4. Multiselect
ms_checks = ui.new_multiselect(
    "Основные контролы",
    "Активные проверки",
    "DNS",
    "IPv6",
    "MTU",
    "Latency",
    default=database.read("checks", ["DNS", "Latency"]) or ["DNS", "Latency"],
    tab_name="Основные",
)

# 5. Textbox + Password/Secret + Listbox
txt_host = ui.new_textbox(
    "Ввод и списки",
    "Целевой хост",
    default=str(database.read("host", "api.lumino-vpn.fun")),
    placeholder="example.com",
    tab_name="Основные",
)
txt_token = ui.new_textbox(
    "Ввод и списки",
    "Секретный ключ (маскируется)",
    default="",
    placeholder="••••••",
    secret=True,
    tab_name="Основные",
)
lst_regions = ui.new_listbox(
    "Ввод и списки",
    "Приоритетный узел",
    "Нидерланды · Амстердам",
    "Германия · Франкфурт",
    "Финляндия · Хельсинки",
    "Сингапур",
    default=0,
    height=4,
    tab_name="Основные",
)

# 6. Вторая вкладка: Hotkey, Color Picker, Label, Button, Reference
lbl_vpn_state = ui.new_label(
    "Телеметрия и цвет",
    "VPN сейчас: неизвестно",
    tone="muted",
    tab_name="Хоткеи и цвет",
)
hk_toggle = ui.new_hotkey(
    "Телеметрия и цвет",
    "Быстрая проверка статуса",
    default="F8",
    mode="toggle",
    inline=False,
    tab_name="Хоткеи и цвет",
)
clr_accent = ui.new_color_picker(
    "Телеметрия и цвет",
    "Цвет пользовательской метки",
    r=230,
    g=232,
    b=235,
    a=255,
    tab_name="Хоткеи и цвет",
)

# Ссылка на встроенную настройку Lumino VPN (GameSense ui.reference)
ref_selected = ui.reference("vpn", "selected_server")


def _sync_indicator(_=None) -> None:
    enabled = bool(ui.get(cb_enabled))
    mode = str(ui.get(cmb_proto))
    state = globals.vpn_state()
    srv = ui.get(ref_selected) or globals.selected_server() or "не выбран"
    ui.set(lbl_vpn_state, f"VPN: {state} · Сервер: {srv}")
    ui.indicator(
        "profile",
        f"{'ON' if enabled else 'OFF'} · {mode}",
        tone="accent" if enabled else "muted",
    )
    database.write("enabled", enabled)
    database.write("timeout_ms", ui.get(sl_delay))
    database.write("route_mode", mode)
    database.write("checks", ui.get(ms_checks))
    database.write("host", str(ui.get(txt_host)))


for _w in (cb_enabled, sl_delay, cmb_proto, ms_checks, txt_host, lst_regions, clr_accent):
    ui.set_callback(_w, _sync_indicator)


def _on_hotkey(item) -> None:
    client.color_log(140, 220, 255, f"Hotkey сработал: active={item.get()}, host={ui.get(txt_host)}")


ui.set_callback(hk_toggle, _on_hotkey)


def _test_preset_roundtrip() -> None:
    exported = config.export()
    client.log(f"Экспортирован пресет ({len(exported)} симв.): {exported[:48]}...")
    client.notify("UI Showcase", "Пресет сформирован (см. консоль)", level="info")


ui.new_button("Телеметрия и цвет", "Проверить config.export()", _test_preset_roundtrip, tab_name="Хоткеи и цвет")


@events.on("load")
def _on_load(_ev) -> None:
    _sync_indicator()
    client.log("01_ui_controls_showcase успешно загружен.")


@events.on("vpn_state_changed")
def _on_vpn_change(_ev) -> None:
    _sync_indicator()


@client.on("console_input")
def _on_console(cmd: str) -> bool:
    if cmd.strip().lower() == "dump":
        client.log(
            f"enabled={ui.get(cb_enabled)}, delay={ui.get(sl_delay)}, "
            f"mode={ui.get(cmb_proto)}, region={ui.get(lst_regions, as_text=True)}, "
            f"color={ui.get(clr_accent)}"
        )
        return True
    return False
