# Troubleshooting Network Issues - Quick Reference

## Симптомы сетевых проблем

### 1. "Network is unreachable" (Errno 101)
```
OSError: [Errno 101] Network is unreachable
Failed to establish a new connection
```

**Причина:** Контейнер не имеет доступа к внешней сети

**Решение:**
```bash
# 1. Проверьте сетевые настройки Docker
docker network ls
docker inspect bridge

# 2. Пересоберите контейнер с правильными настройками
cd /opt/telegram-bots-platform/bots/crop_forecast_bot
git pull
sudo docker-compose down
sudo docker-compose build --no-cache
sudo docker-compose up -d

# 3. Проверьте логи
sudo docker-compose logs -f
```

### 2. "Read timed out" (ReadTimeout)
```
requests.exceptions.ReadTimeout: Read timed out. (read timeout=25)
```

**Причина:** Медленное или нестабильное соединение

**Решение:** Бот автоматически переподключится (до 10 попыток с экспоненциальной задержкой)

**Мониторинг:**
```bash
# Следите за логами
sudo docker-compose logs -f | grep "⚠"
```

### 3. "Max retries exceeded" (ConnectionError)
```
urllib3.exceptions.MaxRetryError: Max retries exceeded
```

**Причина:** Telegram API недоступен или проблема с DNS

**Диагностика:**
```bash
# Проверьте DNS внутри контейнера
sudo docker-compose exec crop_forecast_bot python -c "import socket; print(socket.gethostbyname('api.telegram.org'))"

# Проверьте доступность Telegram API
sudo docker-compose exec crop_forecast_bot curl -I https://api.telegram.org

# Проверьте сетевой режим
sudo docker inspect crop_forecast_bot | grep NetworkMode
```

---

## Быстрая диагностика

### Проверка 1: DNS работает?
```bash
sudo docker-compose exec crop_forecast_bot nslookup api.telegram.org
# Ожидается: IP адрес (например, 149.154.167.220)
```

### Проверка 2: Интернет доступен?
```bash
sudo docker-compose exec crop_forecast_bot ping -c 3 8.8.8.8
# Ожидается: 3 пакета отправлено, 3 получено, 0% потерь
```

### Проверка 3: HTTPS работает?
```bash
sudo docker-compose exec crop_forecast_bot curl -I https://api.telegram.org
# Ожидается: HTTP/2 200
```

### Проверка 4: Бот видит сеть?
```bash
sudo docker-compose logs | grep "✓ Сеть доступна"
# Ожидается: "✓ Сеть доступна (попытка 1/5)"
```

---

## Решения по типу проблемы

### Проблема: Контейнер не видит интернет

**Диагностика:**
```bash
# Проверьте IP адрес контейнера
sudo docker inspect crop_forecast_bot | grep IPAddress

# Проверьте маршрутизацию
sudo docker exec crop_forecast_bot ip route
```

**Решение 1: Перезапустите Docker сервис**
```bash
sudo systemctl restart docker
sudo docker-compose up -d
```

**Решение 2: Проверьте iptables**
```bash
sudo iptables -L DOCKER-USER
# Убедитесь, что нет правил блокирующих исходящий трафик
```

**Решение 3: Используйте host network (временно)**
```yaml
# docker-compose.yml
services:
  crop_forecast_bot:
    network_mode: host  # Используйте сеть хоста напрямую
```

### Проблема: DNS не резолвит домены

**Диагностика:**
```bash
# Проверьте DNS в контейнере
sudo docker exec crop_forecast_bot cat /etc/resolv.conf
```

**Решение: Явно укажите DNS в docker-compose.yml**
```yaml
services:
  crop_forecast_bot:
    dns:
      - 8.8.8.8      # Google DNS
      - 8.8.4.4      # Google DNS (резервный)
      - 1.1.1.1      # Cloudflare DNS (альтернатива)
```

### Проблема: Firewall блокирует Telegram

**Диагностика:**
```bash
# Проверьте исходящие соединения
sudo iptables -L OUTPUT -v -n | grep 443
```

**Решение: Разрешите HTTPS трафик**
```bash
sudo iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
sudo iptables-save > /etc/iptables/rules.v4
```

### Проблема: Telegram API блокирует IP

**Признаки:**
- Другие сайты доступны
- api.telegram.org недоступен
- Возможна блокировка по географии

**Решение: Используйте Telegram Bot API сервер**
```bash
# Разверните локальный Bot API сервер
# https://github.com/tdlib/telegram-bot-api

# Или используйте прокси
export HTTPS_PROXY=http://proxy.example.com:8080
```

---

## Автоматическое восстановление

Бот имеет встроенную логику восстановления:

### Стратегия retry:
1. **Попытка 1:** Немедленная повторная попытка (0s)
2. **Попытка 2:** Задержка 5 секунд
3. **Попытка 3:** Задержка 10 секунд
4. **Попытка 4:** Задержка 20 секунд
5. **Попытка 5:** Задержка 40 секунд
6. **Попытки 6-10:** Задержка 60 секунд (максимум)

### Логи восстановления:
```
✓ Сеть доступна (попытка 1/5)
Бот запущен и подключен к Telegram API...
⚠ Таймаут при чтении от Telegram API, переподключение...
  Повторная попытка через 5 секунд (попытка 1/10)...
✓ Переподключение успешно
```

---

## Мониторинг в реальном времени

### 1. Отслеживание сетевых ошибок
```bash
sudo docker-compose logs -f | grep -E "(⚠|✗|Network|Connection|Timeout)"
```

### 2. Статистика retry
```bash
sudo docker-compose logs | grep "попытка" | tail -20
```

### 3. Healthcheck статус
```bash
watch -n 5 'sudo docker inspect crop_forecast_bot | grep -A 10 Health'
```

### 4. Сетевая активность контейнера
```bash
sudo docker stats crop_forecast_bot --no-stream
```

---

## Профилактика

### 1. Настройте мониторинг
```bash
# Используйте Prometheus + Grafana (встроены в платформу)
# Добавьте алерты на network errors
```

### 2. Регулярно проверяйте логи
```bash
# Создайте cron job для анализа ошибок
*/30 * * * * docker-compose logs --since 30m | grep -c "ConnectionError" > /var/log/bot-errors.log
```

### 3. Настройте автоматический рестарт
```yaml
# docker-compose.yml (уже настроено)
services:
  crop_forecast_bot:
    restart: unless-stopped
```

### 4. Используйте внешний monitoring
```bash
# Проверка доступности бота каждые 5 минут
*/5 * * * * curl -s https://api.telegram.org/bot$TOKEN/getMe > /dev/null || systemctl restart docker
```

---

## Чек-лист перед обращением в поддержку

- [ ] Проверен ли доступ к интернету на хосте?
- [ ] Резолвится ли api.telegram.org внутри контейнера?
- [ ] Работает ли curl https://api.telegram.org из контейнера?
- [ ] Нет ли блокирующих правил в iptables?
- [ ] Правильно ли настроен DNS (8.8.8.8, 8.8.4.4)?
- [ ] Используется ли network_mode: bridge?
- [ ] Актуальна ли версия docker-compose.yml из репозитория?
- [ ] Есть ли в логах сообщение "✓ Сеть доступна"?

**Соберите диагностику:**
```bash
# Сохраните вывод этих команд
sudo docker-compose logs > bot-logs.txt
sudo docker inspect crop_forecast_bot > bot-inspect.txt
sudo docker network ls > docker-networks.txt
sudo iptables -L -n -v > iptables-rules.txt
ip addr show > network-interfaces.txt
cat /etc/resolv.conf > dns-config.txt
```

---

## Контакты

При возникновении проблем:
1. Проверьте README.md и PLATFORM_INTEGRATION.md
2. Изучите логи с помощью этого руководства
3. Создайте issue с диагностической информацией
4. GitHub: https://github.com/f2re/crop_forecast_bot/issues

**Полезные ссылки:**
- Telegram Bot API Status: https://telegram.org/blog
- Docker Network Guide: https://docs.docker.com/network/
- DNS Troubleshooting: https://wiki.archlinux.org/title/Domain_name_resolution
