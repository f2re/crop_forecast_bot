# Команды Telegram-бота

## Почему список команд может не отображаться

Telegram хранит команды отдельно по:

- области действия: общий список, все личные чаты, группы, отдельный чат;
- языку интерфейса пользователя;
- типу кнопки меню.

Более узкая область имеет приоритет над общим списком. Например, старый список для личных чатов или языка `ru` может перекрыть успешно записанный общий список. Кроме того, ранее настроенная кнопка Mini App может скрывать меню команд.

Поэтому production-запуск теперь:

1. записывает один и тот же актуальный список в общий scope;
2. записывает его в scope всех личных чатов;
3. выполняет запись для языка по умолчанию, `ru` и `en`;
4. устанавливает кнопку меню в режим списка команд;
5. читает команды обратно через Telegram API;
6. не объявляет systemd readiness, пока проверка не пройдёт.

## Актуальный список

```text
start - Открыть главное меню
crops - Культуры активного поля
report - Агроотчёт выбранной культуры
risks - Проверить погодные условия
pests - Наблюдение за вредителями
soil - Температура почвы 0–7 см
markers - ОЯ и погодные маркеры вредителей
history - Показать историю предупреждений
help - Показать справку
cancel - Отменить текущий ввод
```

Этот блок является единственным источником для ручной вставки в BotFather. Команды указываются без начального `/`.

## Автоматическая регистрация

При каждом нормальном запуске бот выполняет регистрацию до `READY=1`. В журнале должна появиться строка:

```text
Telegram commands registered and verified: 10 commands, 6 scope/language combinations
```

Проверка:

```bash
sudo journalctl -u crop-forecast-bot.service \
  --since "20 minutes ago" --no-pager | \
  grep -E "Telegram commands|Telegram API verified"
```

## Ручная регистрация на сервере

Применить и проверить:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/telegram-commands.sh --apply
```

Только проверить без изменений:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/telegram-commands.sh --check
```

Получить точный текст для BotFather:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/telegram-commands.sh --botfather
```

Успешная проверка выводит JSON с:

```text
"ok": true
"menu_button": "commands"
```

и шестью комбинациями:

```text
default + общий язык
default + ru
default + en
all_private_chats + общий язык
all_private_chats + ru
all_private_chats + en
```

## Ручная установка через BotFather

1. Откройте `@BotFather`.
2. Отправьте `/setcommands`.
3. Выберите нужного бота.
4. Выберите язык по умолчанию или русский язык, если BotFather предлагает выбор.
5. Вставьте блок:

```text
start - Открыть главное меню
crops - Культуры активного поля
report - Агроотчёт выбранной культуры
risks - Проверить погодные условия
pests - Наблюдение за вредителями
soil - Температура почвы 0–7 см
markers - ОЯ и погодные маркеры вредителей
history - Показать историю предупреждений
help - Показать справку
cancel - Отменить текущий ввод
```

После этого перезапустите диалог с ботом или полностью закройте и снова откройте Telegram. Клиент может некоторое время показывать закэшированный список.

Ручная запись через BotFather является резервным способом. При следующем запуске production-бот повторно применит список из кода.

## Диагностика

Проверить установленный выпуск:

```bash
git -C /opt/crop-forecast-bot/current rev-parse HEAD
```

Проверить службу:

```bash
sudo systemctl status crop-forecast-bot.service --no-pager
```

Проверить ошибки Telegram API:

```bash
sudo journalctl -u crop-forecast-bot.service \
  --since "30 minutes ago" --no-pager | \
  grep -Ei "command|menu button|TelegramBadRequest|TelegramUnauthorized|error"
```

Если `--check` сообщает расхождение, выполните:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/telegram-commands.sh --apply
sudo systemctl restart crop-forecast-bot.service
```

Если регистрация не проходит, systemd не должен получить `READY=1`; причина будет записана в журнал.
