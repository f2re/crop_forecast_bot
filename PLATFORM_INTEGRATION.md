# Интеграция Crop Forecast Bot в Telegram Bots Platform

Это руководство описывает процесс развертывания Crop Forecast Bot на платформе [telegram-bots-platform](https://github.com/f2re/telegram-bots-platform).

## Содержание

1. [Предварительные требования](#предварительные-требования)
2. [Подготовка API ключей](#подготовка-api-ключей)
3. [Развертывание на платформе](#развертывание-на-платформе)
4. [Настройка Google Earth Engine](#настройка-google-earth-engine)
5. [Проверка работоспособности](#проверка-работоспособности)
6. [Мониторинг и логи](#мониторинг-и-логи)
7. [Обновление бота](#обновление-бота)
8. [Устранение неполадок](#устранение-неполадок)

---

## Предварительные требования

### 1. Установленная платформа telegram-bots-platform

Если платформа еще не установлена, следуйте инструкциям:

```bash
# Клонируйте репозиторий платформы
git clone https://github.com/f2re/telegram-bots-platform.git
cd telegram-bots-platform

# Запустите установку
sudo ./install.sh
```

### 2. Системные требования для бота

- **CPU**: минимум 0.5 ядра, рекомендуется 2 ядра
- **RAM**: минимум 1 GB, рекомендуется 4 GB
- **Disk**: минимум 5 GB для данных и моделей
- **Docker**: версия 20.10+
- **Docker Compose**: версия 2.0+

---

## Подготовка API ключей

### 1. Telegram Bot Token

```bash
# Получите токен у @BotFather в Telegram
# Сохраните токен, он понадобится при развертывании
```

### 2. Copernicus CDS API (обязательно)

**Регистрация:**
1. Перейдите на https://cds.climate.copernicus.eu/
2. Создайте аккаунт
3. Примите лицензионные соглашения:
   - ERA5-Land hourly data
   - ERA5 single levels

**Получение API ключа:**
1. Войдите в аккаунт
2. Откройте https://cds.climate.copernicus.eu/api-how-to
3. Скопируйте UID и API key
4. Формат ключа: `UID:API_KEY` (например: `12345:abcdef12-3456-7890-abcd-ef1234567890`)

### 3. OpenRouter API (опционально)

**Для персонализированных LLM рекомендаций:**
1. Зарегистрируйтесь на https://openrouter.ai/
2. Пополните баланс ($5-10 достаточно для начала)
3. Создайте API ключ в разделе Keys
4. Формат: `sk-or-v1-...`

**Стоимость:**
- Claude 3.5 Sonnet: ~$3 за 1M входных токенов
- Средний запрос: ~2000 токенов = $0.006
- 1000 запросов ≈ $6

### 4. Google Earth Engine (опционально)

**Для спутниковых данных (NDVI/LAI):**

См. раздел [Настройка Google Earth Engine](#настройка-google-earth-engine)

---

## Развертывание на платформе

### Вариант 1: Автоматическое развертывание (рекомендуется)

```bash
# Перейдите в директорию платформы
cd /opt/telegram-bots-platform

# Запустите скрипт добавления бота
sudo ./add-bot.sh

# Следуйте инструкциям:
# 1. Введите название бота: crop_forecast_bot
# 2. Укажите Git URL: https://github.com/YOUR_USERNAME/crop_forecast_bot.git
# 3. Укажите ветку: main (или ваша ветка)
```

Скрипт автоматически:
- Клонирует репозиторий в `/opt/telegram-bots-platform/bots/crop_forecast_bot/`
- Создаст `.env` файл из шаблона
- Попросит ввести необходимые API ключи
- Запустит контейнер

### Вариант 2: Ручное развертывание

```bash
# 1. Создайте директорию бота
sudo mkdir -p /opt/telegram-bots-platform/bots/crop_forecast_bot
cd /opt/telegram-bots-platform/bots/crop_forecast_bot

# 2. Клонируйте репозиторий
sudo git clone https://github.com/YOUR_USERNAME/crop_forecast_bot.git .

# 3. Создайте .env файл
sudo cp .env.docker.example .env

# 4. Отредактируйте .env файл
sudo nano .env
```

**Настройка .env файла:**

```bash
# Обязательные параметры
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz  # От @BotFather
CDS_API_KEY=12345:abcdef12-3456-7890-abcd-ef1234567890     # Copernicus CDS

# Опциональные параметры
OPENROUTER_API_KEY=sk-or-v1-your_key_here                 # Для LLM (необязательно)
DATABASE_URL=postgresql://user:password@postgres:5432/crop_forecast_bot_db

# Системные настройки
PYTHONUNBUFFERED=1
LOG_LEVEL=INFO
```

```bash
# 5. Создайте необходимые директории
sudo mkdir -p data/era5 data/satellite data/soil data/training
sudo mkdir -p models logs

# 6. Запустите бота
sudo docker-compose up -d

# 7. Проверьте логи
sudo docker-compose logs -f
```

---

## Настройка Google Earth Engine

Google Earth Engine требует авторизации для доступа к спутниковым данным.

### Вариант 1: Service Account (рекомендуется для продакшна)

```bash
# 1. Создайте проект в Google Cloud Console
# https://console.cloud.google.com/

# 2. Включите Earth Engine API
# https://console.cloud.google.com/apis/library/earthengine.googleapis.com

# 3. Создайте Service Account
# IAM & Admin > Service Accounts > Create Service Account
# Название: crop-forecast-bot-ee
# Роль: Earth Engine Resource Writer

# 4. Создайте JSON ключ
# Нажмите на созданный аккаунт > Keys > Add Key > JSON
# Сохраните файл как ee-service-account.json

# 5. Зарегистрируйте Service Account в Earth Engine
# https://code.earthengine.google.com/
# Assets > NEW > Create service account
# Загрузите JSON ключ

# 6. Скопируйте ключ на сервер
sudo mkdir -p /opt/telegram-bots-platform/bots/crop_forecast_bot/credentials
sudo cp ee-service-account.json /opt/telegram-bots-platform/bots/crop_forecast_bot/credentials/

# 7. Обновите docker-compose.yml
```

Добавьте в `docker-compose.yml`:

```yaml
services:
  crop_forecast_bot:
    environment:
      # Добавьте
      GOOGLE_APPLICATION_CREDENTIALS: /app/credentials/ee-service-account.json
      EE_PROJECT: your-gcp-project-id

    volumes:
      # Добавьте
      - ./credentials:/app/credentials:ro
```

### Вариант 2: User Account (для разработки)

```bash
# 1. На локальной машине выполните авторизацию
earthengine authenticate

# 2. Скопируйте credentials на сервер
# Файлы находятся в ~/.config/earthengine/

# Linux/Mac:
scp -r ~/.config/earthengine user@server:/opt/telegram-bots-platform/bots/crop_forecast_bot/

# 3. Обновите docker-compose.yml
```

Убедитесь, что в `docker-compose.yml` есть:

```yaml
volumes:
  - ./earthengine:/root/.config/earthengine:ro
```

### Вариант 3: Без Earth Engine (базовый режим)

Бот будет работать без спутниковых данных, используя только климатические и почвенные данные:

```bash
# Удалите или закомментируйте в docker-compose.yml:
# - ${HOME}/.config/earthengine:/root/.config/earthengine:ro
```

---

## Проверка работоспособности

### 1. Проверка статуса контейнера

```bash
cd /opt/telegram-bots-platform/bots/crop_forecast_bot

# Статус контейнера
sudo docker-compose ps

# Должно быть:
# NAME                      STATUS
# crop_forecast_bot         Up (healthy)
```

### 2. Проверка логов

```bash
# Просмотр последних логов
sudo docker-compose logs --tail=50

# Отслеживание логов в реальном времени
sudo docker-compose logs -f

# Проверьте наличие:
# ✓ "Bot started successfully"
# ✓ "Polling started"
# ✗ Нет ошибок импорта модулей
# ✗ Нет ошибок подключения к API
```

### 3. Тестирование бота

1. Откройте Telegram
2. Найдите вашего бота по username
3. Отправьте `/start`
4. Ожидаемый ответ: приветственное сообщение с кнопками
5. Нажмите "Рекомендации по культурам 🌾"
6. Отправьте геолокацию
7. Дождитесь анализа (2-3 минуты)

**Успешный тест:**
- Бот отвечает на `/start`
- Принимает геолокацию
- Загружает климатические данные
- Возвращает топ-3 культуры с рейтингами

### 4. Healthcheck

```bash
# Проверка health-статуса
sudo docker inspect crop_forecast_bot | grep -A 10 Health

# Должно быть: "Status": "healthy"
```

---

## Мониторинг и логи

### Grafana Dashboard

Платформа включает Grafana для мониторинга:

```
URL: http://your-server-ip:3000
Логин: admin
Пароль: (установлен при настройке платформы)
```

**Метрики для crop_forecast_bot:**
- CPU Usage
- Memory Usage
- Container Restarts
- Network I/O

### Логирование

Логи сохраняются в трех местах:

1. **Docker logs (stdout)**
   ```bash
   sudo docker-compose logs crop_forecast_bot
   ```

2. **Файловые логи** (`/app/logs/`)
   ```bash
   sudo tail -f logs/bot.log
   ```

3. **JSON logs** (для анализа)
   ```bash
   sudo docker inspect --format='{{.LogPath}}' crop_forecast_bot
   ```

### Настройка ротации логов

Уже настроено в `docker-compose.yml`:
- Максимальный размер файла: 10 MB
- Количество файлов: 3
- Формат: JSON

---

## Обновление бота

### Обновление кода

```bash
cd /opt/telegram-bots-platform/bots/crop_forecast_bot

# 1. Остановите бота
sudo docker-compose down

# 2. Обновите код
sudo git pull origin main

# 3. Пересоберите образ
sudo docker-compose build --no-cache

# 4. Запустите бота
sudo docker-compose up -d

# 5. Проверьте логи
sudo docker-compose logs -f
```

### Обновление зависимостей

```bash
# Если обновился requirements.txt
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

### Обновление моделей ML

```bash
# 1. Обучите новую модель (локально или на сервере)
python scripts/train_rf_model.py

# 2. Скопируйте модель на сервер
scp models/crop_rf_model.pkl user@server:/opt/telegram-bots-platform/bots/crop_forecast_bot/models/

# 3. Перезапустите бота
sudo docker-compose restart
```

---

## Устранение неполадок

### Проблема: Контейнер не запускается

```bash
# Проверьте логи
sudo docker-compose logs

# Частые причины:
# 1. Неверный TELEGRAM_BOT_TOKEN
# 2. Отсутствует .env файл
# 3. Недостаточно памяти
```

**Решение:**
```bash
# Проверьте .env
cat .env | grep TELEGRAM_BOT_TOKEN

# Проверьте память
free -h

# Увеличьте лимиты в docker-compose.yml при необходимости
```

### Проблема: Ошибка "CDS API authentication failed"

```bash
# Проверьте формат ключа
cat .env | grep CDS_API_KEY
# Должно быть: UID:API_KEY (без пробелов)
```

**Решение:**
```bash
# Обновите .env
sudo nano .env
# CDS_API_KEY=12345:your-api-key-here

# Перезапустите
sudo docker-compose restart
```

### Проблема: Нет данных от спутников

```bash
# Проверьте логи
sudo docker-compose logs | grep -i "earth engine"

# Частые причины:
# 1. Не настроен Earth Engine
# 2. Истек срок авторизации
# 3. Превышена квота запросов
```

**Решение:**
```bash
# Проверьте credentials
ls -la earthengine/

# Переавторизуйтесь (см. раздел настройки Earth Engine)
```

### Проблема: Медленная работа

```bash
# Проверьте использование ресурсов
sudo docker stats crop_forecast_bot

# Если CPU > 90% или Memory близко к лимиту
```

**Решение:**
```bash
# Увеличьте лимиты в docker-compose.yml
nano docker-compose.yml

# Измените:
deploy:
  resources:
    limits:
      cpus: '4.0'      # Было 2.0
      memory: 8G       # Было 4G
```

### Проблема: Ошибки импорта модулей

```bash
# Проверьте, что образ собран правильно
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

### Проблема: База данных недоступна

```bash
# Если используете PostgreSQL платформы
sudo docker ps | grep postgres

# Проверьте подключение
sudo docker-compose exec crop_forecast_bot python -c "
import os
from sqlalchemy import create_engine
engine = create_engine(os.getenv('DATABASE_URL'))
print('Database connected!')
"
```

---

## Интеграция с платформой

### Nginx и SSL

Платформа автоматически настраивает Nginx и SSL для веб-интерфейсов. Для бота настройка не требуется.

### PostgreSQL

Если вашему боту нужна БД:

```bash
# Платформа создаст БД автоматически
# Название: crop_forecast_bot_db
# URL будет в переменной DATABASE_URL
```

Для использования БД добавьте в код:

```python
import os
from sqlalchemy import create_engine

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
    # Ваш код для работы с БД
```

### Мониторинг Prometheus

Для экспорта метрик добавьте в код:

```python
from prometheus_client import Counter, Gauge, start_http_server

# Метрики
requests_total = Counter('bot_requests_total', 'Total requests')
active_users = Gauge('bot_active_users', 'Active users')

# Запустите HTTP сервер для метрик
start_http_server(8000)
```

Добавьте в `docker-compose.yml`:

```yaml
ports:
  - "8000:8000"  # Для Prometheus метрик
```

---

## Резервное копирование

### Автоматическое резервное копирование данных

```bash
# Создайте скрипт резервного копирования
sudo nano /opt/telegram-bots-platform/backup-crop-bot.sh
```

```bash
#!/bin/bash
BOT_DIR="/opt/telegram-bots-platform/bots/crop_forecast_bot"
BACKUP_DIR="/opt/backups/crop_forecast_bot"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Бэкап данных
tar -czf $BACKUP_DIR/data_$DATE.tar.gz $BOT_DIR/data/

# Бэкап моделей
tar -czf $BACKUP_DIR/models_$DATE.tar.gz $BOT_DIR/models/

# Удалить старые бэкапы (старше 30 дней)
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
```

```bash
# Сделайте скрипт исполняемым
sudo chmod +x /opt/telegram-bots-platform/backup-crop-bot.sh

# Добавьте в cron (ежедневно в 3:00)
sudo crontab -e
# Добавьте строку:
0 3 * * * /opt/telegram-bots-platform/backup-crop-bot.sh >> /var/log/crop-bot-backup.log 2>&1
```

---

## Масштабирование

### Горизонтальное масштабирование

Для обработки большой нагрузки:

```yaml
# docker-compose.yml
services:
  crop_forecast_bot:
    deploy:
      replicas: 3  # Запустить 3 экземпляра
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
```

### Кэширование данных

Добавьте Redis для кэширования результатов:

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: crop_forecast_redis
    restart: unless-stopped
    networks:
      - bot_network

  crop_forecast_bot:
    depends_on:
      - redis
    environment:
      REDIS_URL: redis://redis:6379/0
```

---

## Поддержка

- **Документация бота**: README.md в репозитории
- **Платформа**: https://github.com/f2re/telegram-bots-platform/issues
- **API Copernicus**: https://cds.climate.copernicus.eu/support
- **Earth Engine**: https://developers.google.com/earth-engine/support

---

## Лицензия

Этот бот распространяется под лицензией проекта. См. LICENSE в репозитории.
