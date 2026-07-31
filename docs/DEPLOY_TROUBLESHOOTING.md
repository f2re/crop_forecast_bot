# Диагностика native deployment

## Preflight сообщает `Path is not writable`

Native deployment запускает `src.ops.doctor --runtime` от системного пользователя `cropbot`. Это намеренная проверка: каталоги, доступные только root, не должны проходить до запуска systemd.

Для штатной установки должны быть доступны:

```text
/var/lib/crop-forecast-bot/data
/var/lib/crop-forecast-bot/models
/var/cache/crop-forecast-bot
/var/log/crop-forecast-bot
/run/crop-forecast-bot
```

Проверка цепочки прав:

```bash
release="$(find /opt/crop-forecast-bot/releases -mindepth 1 -maxdepth 1 -type d \
  -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"

readlink -f "${release}/data"
namei -l "${release}/data"
namei -l /run/crop-forecast-bot

stat -c '%A %U:%G %n' \
  /var/lib/crop-forecast-bot \
  /var/lib/crop-forecast-bot/data \
  /var/cache/crop-forecast-bot \
  /var/log/crop-forecast-bot \
  /run/crop-forecast-bot

sudo -u cropbot /usr/bin/test -w /var/lib/crop-forecast-bot/data && echo 'data: writable'
sudo -u cropbot /usr/bin/test -w /run/crop-forecast-bot && echo 'runtime: writable'
```

Проверка файловой системы:

```bash
findmnt -no TARGET,FSTYPE,OPTIONS -T /var/lib/crop-forecast-bot/data
findmnt -no TARGET,FSTYPE,OPTIONS -T /run/crop-forecast-bot
```

`ro` запрещает запись. `noexec` не мешает обычной записи, но мешает запуску Python virtualenv, если сам venv расположен на таком разделе.

## Почему `data` мог стать root-owned

Репозиторий содержит seed-каталог `data`. Старый deployment копировал его через `cp -a` от root; сохранение метаданных могло заменить владельца уже созданного persistent-каталога. Новый deploy после копирования повторно устанавливает владельца `cropbot:cropbot`, режим `0750` и проверяет запись от имени `cropbot`.

## Почему отсутствовал `/run/crop-forecast-bot`

Обычно этот каталог создаёт systemd через `RuntimeDirectory=`. Deployment preflight выполняется до первого запуска сервиса, поэтому каталог ещё отсутствовал. Новый deploy создаёт его до preflight; systemd продолжает управлять им во время штатного запуска.

## Безопасное ручное восстановление

Для старого checkout до получения исправления:

```bash
sudo install -d -m 0750 -o cropbot -g cropbot \
  /var/lib/crop-forecast-bot \
  /var/lib/crop-forecast-bot/data \
  /var/lib/crop-forecast-bot/data/literature \
  /var/lib/crop-forecast-bot/models \
  /var/cache/crop-forecast-bot \
  /var/log/crop-forecast-bot \
  /run/crop-forecast-bot
```

Затем повторить deployment из актуального `main`:

```bash
git switch main
git pull --ff-only origin main
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Не используйте `bash -x` с deployment-скриптом: shell trace может вывести Telegram token и пароль PostgreSQL.
