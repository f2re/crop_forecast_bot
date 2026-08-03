# Диагностика обновления и перезапуска

## Две разные копии проекта

Рабочий каталог разработчика:

```text
~/crop_forecast_bot
```

и установленный выпуск:

```text
/opt/crop-forecast-bot/releases/<время>-<sha>
/opt/crop-forecast-bot/current -> активный выпуск
```

не являются одним каталогом. `git pull` в домашнем каталоге только обновляет исходники для просмотра и ручного запуска установщика. Служба systemd запускает код из `/opt/crop-forecast-bot/current`.

## Почему `update.sh` может сообщить, что обновление не требуется

Скрипт сравнивает:

```text
SHA ветки main на GitHub
SHA каталога /opt/crop-forecast-bot/current
```

Если они совпадают, новый clone и установка зависимостей не нужны. Обычно это означает, что systemd timer уже установил выпуск раньше ручного запуска.

Актуальный скрипт дополнительно проверяет:

- активна ли служба;
- свежий ли heartbeat;
- совпадает ли реальный рабочий каталог процесса с `/opt/crop-forecast-bot/current`.

Если symlink уже новый, а процесс ещё работает из старого выпуска, текущий выпуск повторно проверяется и служба перезапускается.

## Проверить фактически загруженный выпуск

```bash
service=crop-forecast-bot.service
pid="$(systemctl show "$service" -p MainPID --value)"
current="$(readlink -f /opt/crop-forecast-bot/current)"
running="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"

printf 'PID:       %s\n' "$pid"
printf 'current:   %s\n' "$current"
printf 'process:   %s\n' "$running"
printf 'current SHA: '
git -C "$current" rev-parse HEAD
if [[ -n "$running" && -d "$running/.git" ]]; then
  printf 'process SHA: '
  git -C "$running" rev-parse HEAD
fi

systemctl show "$service" \
  -p ActiveState \
  -p SubState \
  -p ExecMainStartTimestamp \
  -p MainPID
```

Нормальное состояние:

```text
current == process
current SHA == origin/main SHA
ActiveState=active
SubState=running
```

## Принудительно перезапустить уже установленный выпуск

Обычный перезапуск без повторного клонирования:

```bash
sudo systemctl restart crop-forecast-bot.service
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## Полностью переустановить тот же коммит

Это нужно только при подозрении на повреждённые файлы выпуска, неверные unit-файлы или незавершённую ручную операцию:

```bash
cd ~/crop_forecast_bot
sudo FORCE_REDEPLOY=true bash scripts/update.sh main
```

Полная переустановка:

1. повторно проверяет зелёный GitHub CI;
2. клонирует точный SHA в новый release-каталог;
3. проверяет или создаёт Python-окружение;
4. применяет миграции Alembic;
5. запускает runtime preflight;
6. переустанавливает systemd unit-файлы;
7. переключает symlink;
8. перезапускает службу;
9. ждёт свежий heartbeat;
10. откатывает выпуск при ошибке.

`TOKEN_FILE` для `update.sh` не используется: обновление читает уже созданный `/etc/crop-forecast-bot.env`. `TOKEN_FILE` нужен при первоначальном `deploy.sh`.

## Журналы

```bash
sudo journalctl -u crop-forecast-bot-update.service -n 250 --no-pager
sudo journalctl -u crop-forecast-bot.service --since '30 minutes ago' --no-pager
```

Проверка таймера:

```bash
sudo systemctl status crop-forecast-bot-update.timer --no-pager
sudo systemctl list-timers crop-forecast-bot-update.timer
```
