"""Тест 02: Neverlose-стиль ui.settings(), шестерёнки на строках item.create(), depends() и inactive()."""

LUMINO_META = {
    "id": "test-02-neverlose-gear",
    "name": "Тест 02 — Шестерёнки и Depends",
    "description": "Показывает вложенные меню на строках (item.create()), цепочку depends() и блокировку inactive().",
    "version": "1.0.0",
    "author": "Lumino QA",
    "permissions": ["notifications", "config"],
    "has_settings": True,
}

from lumino import client, events, ui

settings = ui.settings("Neverlose Gear Demo", "Вложенные шестерёнки, зависимости и блокировки")
tab_rules = settings.tab("Правила")
tab_diag = settings.tab("Диагностика")

grp_main = tab_rules.group("Умная фильтрация")

master = grp_main.checkbox(
    "Включить фильтр пакетов",
    default=True,
    tooltip="Главный рубильник: скрывает зависимые пункты при выключении",
)

# На этой строке появится иконка шестерёнки (Neverlose item.create)
master_gear = master.create("Параметры фильтра пакетов")
sub_threshold = master_gear.slider("Порог срабатывания", 10, 500, default=120, unit=" КБ")
sub_aggressive = master_gear.checkbox("Строгий режим (Drop без повтора)", default=False)
# Вложенная 2-го уровня шестерёнка внутри модалки!
nested_gear = sub_aggressive.gear("Тонкая настройка Drop")
nested_retries = nested_gear.slider("Повторов до блокировки", 1, 10, default=3, unit=" раз")

# Зависимые пункты (.depends) — появляются только если master == True
route_profile = grp_main.combo(
    "Профиль фильтрации",
    "Сбалансированный",
    "Минимальная задержка",
    "Только игры",
    default="Сбалансированный",
).depends(master, True)

custom_dns = grp_main.textbox(
    "Пользовательский DNS",
    default="1.1.1.1",
    placeholder="1.1.1.1 или 8.8.8.8",
).depends(route_profile, "Минимальная задержка")

# Пункт, временно заблокированный (.inactive) пока переключатель ниже не активирован
allow_experimental = grp_main.checkbox("Разрешить экспериментальный режим", default=False)
experimental_mtu = (
    grp_main.slider("Кастомный MTU", 1200, 1500, default=1380, unit=" B")
    .inactive(True, reason="Сначала включите «Разрешить экспериментальный режим»")
)


def _sync_experimental(item) -> None:
    enabled = bool(item.get())
    experimental_mtu.inactive(
        not enabled,
        reason="" if enabled else "Сначала включите «Разрешить экспериментальный режим»",
    )


allow_experimental.callback(_sync_experimental)

grp_diag = tab_diag.group("Отчёт по текущим значениям")
summary_lbl = grp_diag.label("Ожидание...", tone="muted")


def _update_summary(_=None) -> None:
    text = (
        f"master={master.get()}, threshold={sub_threshold.get()} КБ, "
        f"strict={sub_aggressive.get()} (retries={nested_retries.get()}), "
        f"profile={route_profile.get()}, mtu={experimental_mtu.get()}"
    )
    summary_lbl.set(text)
    ui.indicator("filter", f"Фильтр: {'ON' if master.get() else 'OFF'}", tone="accent" if master.get() else "muted")


for _item in (master, sub_threshold, sub_aggressive, nested_retries, route_profile, custom_dns, experimental_mtu):
    _item.callback(_update_summary)

grp_diag.button(
    "Вывести состояние в консоль",
    lambda: client.color_log(170, 240, 170, summary_lbl.get()),
)


@events.on("load")
def _on_load(_ev) -> None:
    _update_summary()
    client.log("02_neverlose_gear_and_depends готов: проверьте иконки шестерёнок у строк!")
