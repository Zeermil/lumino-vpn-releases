# Тестовые расширения Lumino VPN

Каталог `extensions.txt` предназначен для проверки системы **Дополнения (Extensions API)** в Lumino VPN 2.0.

## Список расширений

| Файл | ID | Что проверяет | Настройки (шестерёнка) |
| --- | --- | --- | --- |
| `network_diagnostics.py` | `lumino-net-diagnostics` | Внешний IP (напрямую и через SOCKS5 VPN), пинг серверов, `ui.indicator` с прогрессом, буфер обмена, БД, консольные команды | Да (включая подменю) |
| `auto_game_tunnel.py` | `auto-game-tunnel` | Автопереключение на лучший сервер по пингу, Split Tunnel и `traffic_tick` | Да |
| `antigravity_signin_unlock.py` | `antigravity-unlock` | Патч, управление процессами/Split Tunnel и CLI (`--self-test`) | Да |
| `01_ui_controls_showcase.py` | `test-01-ui-showcase` | Все 10 типов UI-контролов (`checkbox`, `slider`, `combo`, `multiselect`, `textbox`, `listbox`, `button`, `label`, `hotkey`, `color`) и экспорт/импорт пресетов | Да |
| `02_neverlose_gear_and_depends.py` | `test-02-neverlose-gear` | Вложенные шестерёнки на строках (`item.create()`), зависимости `depends()`, блокировка `inactive()` | Да |
| `03_vpn_events_and_split_tunnel.py` | `test-03-vpn-split-http` | События `vpn_connected`/`vpn_disconnected`, Split Tunnel и HTTP через SOCKS5 | Да |
| `04_background_worker_no_gear.py` | `test-04-background-no-gear` | Фоновое расширение без UI и без иконки настроек | Нет |
| `05_plain_cli_no_sdk.py` | `05_plain_cli_no_sdk` | Обычный Python CLI-скрипт без `import lumino` (авто-генерация UI по `argparse`) | Да (авто-CLI) |
