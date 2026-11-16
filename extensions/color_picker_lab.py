"""QA: чистая страница только с колор-пикером — 2D-поле, пресеты, свои цвета и HEX."""

LUMINO_META = {
    "id": "color-picker-lab",
    "name": "Колор-пикер — тест",
    "description": "Только колор-пикер: 2D-поле, пресеты, сохранённые цвета и HEX. Без VPN и фоновых задач.",
    "version": "1.0.0",
    "author": "Lumino QA",
    "permissions": ["config", "notifications"],
    "has_settings": True,
    "min_app_version": "1.9.0",
}

from lumino import client, database, events, ui

ui.settings("Колор-пикер", "2D-поле · пресеты · свои цвета · HEX")

DEFAULT_PRIMARY = (76, 125, 255, 255)
DEFAULT_SECONDARY = (255, 92, 122, 255)
DEFAULT_ACCENT = (92, 230, 155, 255)


def _rgba(raw, fallback):
    """Accept the list/tuple shape the host returns and keep it inside 0..255."""
    try:
        values = list(raw)
        if len(values) == 3:
            values.append(255)
        if len(values) != 4:
            return fallback
        return tuple(max(0, min(255, int(part))) for part in values)
    except (TypeError, ValueError):
        return fallback


def _hex(rgba):
    return "#{:02X}{:02X}{:02X}".format(rgba[0], rgba[1], rgba[2])


def _stored(key, fallback):
    return _rgba(database.read(key, list(fallback)), fallback)


primary = ui.new_color_picker(
    "Цвета",
    "Основной цвет",
    *_stored("primary", DEFAULT_PRIMARY),
    tab_name="Пикер",
)
secondary = ui.new_color_picker(
    "Цвета",
    "Дополнительный цвет",
    *_stored("secondary", DEFAULT_SECONDARY),
    tab_name="Пикер",
)
accent = ui.new_color_picker(
    "Цвета",
    "Акцентный цвет",
    *_stored("accent", DEFAULT_ACCENT),
    tab_name="Пикер",
)

summary = ui.new_label("Сводка", "…", tone="accent", tab_name="Пикер")
hint = ui.new_label(
    "Сводка",
    "Клик по свотчу открывает 2D-пикер. Сохранённые цвета (иконка-сетка внизу пикера) общие для всех трёх строк.",
    tone="muted",
    tab_name="Пикер",
)


def _sync(_event=None):
    values = {
        "primary": _rgba(ui.get(primary), DEFAULT_PRIMARY),
        "secondary": _rgba(ui.get(secondary), DEFAULT_SECONDARY),
        "accent": _rgba(ui.get(accent), DEFAULT_ACCENT),
    }
    for key, rgba in values.items():
        database.write(key, list(rgba))
    text = (
        "Основной {} · Дополнительный {} · Акцент {}".format(
            _hex(values["primary"]),
            _hex(values["secondary"]),
            _hex(values["accent"]),
        )
    )
    ui.set(summary, text)
    ui.indicator("color", _hex(values["primary"]), tone="accent")


def _reset(_event=None):
    ui.set(primary, *DEFAULT_PRIMARY)
    ui.set(secondary, *DEFAULT_SECONDARY)
    ui.set(accent, *DEFAULT_ACCENT)
    _sync()


def _log_colors(_event=None):
    _sync()
    client.color_log(140, 220, 255, "color-picker-lab:", ui.get(summary))


for _item in (primary, secondary, accent):
    ui.set_callback(_item, _sync)

ui.new_button("Действия", "Сбросить цвета", _reset, tab_name="Пикер")
ui.new_button("Действия", "Записать цвета в консоль", _log_colors, tab_name="Пикер")


@events.on("load")
def _on_load(_event=None):
    _sync()
    client.log("color-picker-lab загружен: " + str(ui.get(summary)))
