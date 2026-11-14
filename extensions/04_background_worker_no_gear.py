"""Тест 04: Чистый фоновый скрипт БЕЗ UI-настроек (проверяет, что иконка шестерёнки скрыта)."""

LUMINO_META = {
    "id": "test-04-background-no-gear",
    "name": "Тест 04 — Фоновый (без шестерёнки)",
    "description": "Не вызывает ui.settings/ui.new_*: работает в фоне, пишет логи и слушает события без кнопки настроек.",
    "version": "1.0.0",
    "author": "Lumino QA",
    "permissions": ["vpn.read", "notifications"],
    "has_settings": False,
}

from lumino import client, events, globals


def _heartbeat() -> None:
    client.log(
        f"[BackgroundWorker] uptime={globals.uptime_sec()}s, "
        f"vpn={globals.vpn_state()}, ping={globals.ping_ms()}ms"
    )
    client.delay_call(15.0, _heartbeat)


@events.on("load")
def _on_load(_ev) -> None:
    client.color_log(180, 220, 255, "Фоновый воркер запущен (UI настроек не зарегистрирован).")
    client.delay_call(2.0, _heartbeat)


@events.on("vpn_connected")
def _on_connect(ev) -> None:
    client.notify(
        "Фоновый наблюдатель",
        f"VPN подключён: {ev.get('server') or globals.active_server()}",
        level="info",
    )


@events.on("unload")
def _on_unload(_ev) -> None:
    client.log("[BackgroundWorker] остановка по сигналу хоста.")
