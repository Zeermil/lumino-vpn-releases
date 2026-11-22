# Каталог расширений Lumino VPN (v2)

В этой папке публикуются пакеты расширений нового формата `.luminoext` с манифестом `manifest.json`, SHA-256 картой файлов и криптографической подписью `signature.ed25519` (ключ `lumino-official-v1`).

- Индекс каталога: `extensions.txt` (JSON со списком пакетов, `format: "luminoext"`, `signature_required: true`).
- Папка `../extensions/` оставлена без изменений для обратной совместимости со старыми версиями клиента, которые загружают одиночные `.py` файлы.

## Локальная сборка и подпись каталога

Сборка и подпись выполняются локально из монорепозитория Lumino VPN (GitHub Actions не используется):

```powershell
python windows/extensions-api/tools/audit_and_pack.py build-catalog <src_dir> --out-dir extensions-v2 --key-id lumino-official-v1
```

Перед публикацией каждый пакет проверяется утилитой `lumino-ext.exe verify <file>.luminoext`.
