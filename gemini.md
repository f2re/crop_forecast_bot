# Gemini AI Agent System — Crop Forecast Bot

> Файл конфигурации мультиагентной системы на базе Google Gemini для реализации всех функциональных планов проекта `crop_forecast_bot`.

---

## 📐 Архитектура системы агентов

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT                           │
│              (gemini-2.0-flash / gemini-2.5-pro)                │
│  Управляет маршрутизацией запросов между специализированными    │
│  агентами, агрегирует результаты, формирует финальный ответ     │
└──────────────┬──────────────────────────────────────────────────┘
               │
   ┌───────────┼───────────────────┬──────────────────┐
   ▼           ▼                   ▼                  ▼
┌──────┐  ┌─────────┐  ┌────────────────┐  ┌──────────────┐
│ DATA │  │   RAG   │  │   FORECAST     │  │  SCHEDULER   │
│AGENT │  │  AGENT  │  │    AGENT       │  │    AGENT     │
└──────┘  └─────────┘  └────────────────┘  └──────────────┘
```

---

## 🤖 Описание агентов

### 1. OrchestratorAgent — Главный оркестратор

**Файл**: `src/agents/orchestrator_agent.py`  
**Модель**: `gemini-2.5-pro` (для сложных агрегаций)  
**Роль**: Принимает входящий запрос пользователя из Telegram, определяет нужных субагентов, собирает результаты в единый ответ.

```python
from google import genai
from google.genai import types

ORCHESTRATOR_INSTRUCTION = """
Ты — главный агроном-аналитик системы Crop Forecast Bot.
Твоя задача — координировать анализ агрономических данных.

При получении запроса:
1. Определи тип запроса: прогноз культур / агрономический совет / анализ погоды / уведомление
2. Делегируй подзадачи нужным субагентам через инструменты
3. Агрегируй результаты в структурированный ответ на русском языке
4. Форматируй ответ для Telegram (markdown, эмодзи, без HTML)

Всегда отвечай на русском языке. Используй агрономическую терминологию.
"""

orchestrator = genai.Client().aio.live.connect(
    model="gemini-2.5-pro",
    config=types.LiveConnectConfig(
        system_instruction=ORCHESTRATOR_INSTRUCTION,
        tools=[data_agent_tool, rag_agent_tool, forecast_agent_tool, scheduler_agent_tool]
    )
)
```

---

### 2. DataCollectionAgent — Агент сбора данных

**Файл**: `src/agents/data_collection_agent.py`  
**Модель**: `gemini-2.0-flash`  
**Роль**: Сбор и предобработка климатических, спутниковых и почвенных данных по координатам.

**Инструменты (Tools)**:

```python
from google.genai import types

tools = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="fetch_era5_climate_data",
            description="Получить климатические данные ERA5-Land по координатам за период",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "lat": types.Schema(type=types.Type.NUMBER, description="Широта"),
                    "lon": types.Schema(type=types.Type.NUMBER, description="Долгота"),
                    "start_date": types.Schema(type=types.Type.STRING, description="Дата начала YYYY-MM-DD"),
                    "end_date": types.Schema(type=types.Type.STRING, description="Дата конца YYYY-MM-DD"),
                },
                required=["lat", "lon"]
            )
        ),
        types.FunctionDeclaration(
            name="fetch_satellite_ndvi",
            description="Получить индексы NDVI и LAI из Google Earth Engine (MODIS/Sentinel-2)",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "lat": types.Schema(type=types.Type.NUMBER),
                    "lon": types.Schema(type=types.Type.NUMBER),
                    "date_range_days": types.Schema(type=types.Type.INTEGER, description="Период в днях"),
                },
                required=["lat", "lon"]
            )
        ),
        types.FunctionDeclaration(
            name="fetch_soil_data",
            description="Получить почвенные характеристики из SoilGrids API",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "lat": types.Schema(type=types.Type.NUMBER),
                    "lon": types.Schema(type=types.Type.NUMBER),
                },
                required=["lat", "lon"]
            )
        ),
        types.FunctionDeclaration(
            name="calculate_agro_indices",
            description="Рассчитать агроиндексы: GDD, SPI, ГТК, ET0-баланс",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "climate_data": types.Schema(type=types.Type.STRING, description="JSON с климатическими данными"),
                    "indices": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="Список индексов для расчёта: gdd, spi, gtc, et0"
                    ),
                }
            )
        ),
    ])
]

DATA_AGENT_INSTRUCTION = """
Ты — специалист по сбору агрометеорологических данных.
Твоя задача — получить полный набор данных для агрономического анализа по указанным координатам.

Алгоритм работы:
1. Запроси климатические данные ERA5-Land за последние 12 месяцев
2. Запроси спутниковые данные NDVI/LAI за последние 30 дней
3. Запроси почвенные данные (pH, текстура, органика)
4. Рассчитай агроиндексы: GDD, SPI, ГТК, ET0
5. Верни структурированный JSON с данными

При ошибке API — используй fallback: Open-Meteo для климата, предиктивные модели для NDVI.
Всегда указывай источник данных и временной период.
"""
```

---

### 3. RAGAdvisorAgent — Агент агрономических консультаций

**Файл**: `src/agents/rag_advisor_agent.py`  
**Модель**: `gemini-2.0-flash` + `text-embedding-004`  
**Роль**: Поиск и генерация агрономических рекомендаций на основе RAG (ChromaDB + научная литература).

**Инструменты**:

```python
RAG_TOOLS = [
    types.FunctionDeclaration(
        name="search_agro_knowledge_base",
        description="Поиск в базе знаний по агрономии (FAO, ГОСТы, научные статьи)",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(type=types.Type.STRING, description="Запрос на русском"),
                "top_k": types.Schema(type=types.Type.INTEGER, description="Количество результатов"),
                "filter_category": types.Schema(
                    type=types.Type.STRING,
                    description="Фильтр категории: crop_care, diseases, soil, climate"
                ),
            },
            required=["query"]
        )
    ),
    types.FunctionDeclaration(
        name="get_crop_growing_guide",
        description="Получить полное руководство по выращиванию культуры",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "crop_name": types.Schema(type=types.Type.STRING, description="Название культуры на русском"),
                "region_climate": types.Schema(type=types.Type.STRING, description="Климатическая зона"),
            },
            required=["crop_name"]
        )
    ),
]

RAG_AGENT_INSTRUCTION = """
Ты — опытный агроном-консультант с доступом к научной библиотеке.
Отвечай на вопросы фермеров, используя поиск по базе знаний.

При ответе:
1. Всегда делай поиск в базе знаний по теме запроса
2. Синтезируй ответ из найденных источников
3. Указывай практические рекомендации (сроки, дозы, методы)
4. Учитывай текущие агроиндексы поля при рекомендациях
5. Если данных недостаточно — честно сообщи об этом

Язык ответа — русский. Стиль — дружелюбный, профессиональный.
"""
```

---

### 4. ForecastAgent — Агент прогнозирования культур

**Файл**: `src/agents/forecast_agent.py`  
**Модель**: `gemini-2.0-flash`  
**Роль**: Генерация рекомендаций по выбору оптимальных культур на основе ML-модели и AI-анализа.

**Инструменты**:

```python
FORECAST_TOOLS = [
    types.FunctionDeclaration(
        name="run_ml_crop_forecast",
        description="Запустить ML Random Forest модель для прогноза топ-3 культур",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "feature_vector": types.Schema(
                    type=types.Type.STRING,
                    description="JSON с признаками: температура, осадки, NDVI, pH почвы, ГТК, GDD"
                ),
            },
            required=["feature_vector"]
        )
    ),
    types.FunctionDeclaration(
        name="get_market_crop_prices",
        description="Получить текущие рыночные цены на культуры в регионе",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "region": types.Schema(type=types.Type.STRING),
                "crops": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING)
                ),
            }
        )
    ),
    types.FunctionDeclaration(
        name="analyze_crop_risks",
        description="Анализировать риски для культур: заморозки, засуха, болезни",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "crop_name": types.Schema(type=types.Type.STRING),
                "weather_forecast": types.Schema(type=types.Type.STRING, description="JSON прогноза погоды"),
                "soil_data": types.Schema(type=types.Type.STRING),
            }
        )
    ),
]

FORECAST_AGENT_INSTRUCTION = """
Ты — эксперт по агрономическому прогнозированию.
Твоя задача — определить оптимальные культуры для поля на основе данных.

Алгоритм:
1. Запусти ML-модель для базового прогноза
2. Проанализируй риски для топ-3 культур (заморозки, засуха, вредители)
3. Учти рыночную стоимость при приоритизации
4. Сформируй структурированный отчёт с рейтингами (0-100%)
5. Добавь агрономические рекомендации по каждой культуре

Формат вывода: JSON с полями crop_name, score, risks, recommendations.
"""
```

---

### 5. SchedulerAgent — Агент планировщика уведомлений

**Файл**: `src/agents/scheduler_agent.py`  
**Модель**: `gemini-2.0-flash`  
**Роль**: Генерация персонализированных алертов и ежедневных отчётов для пользователей.

**Инструменты**:

```python
SCHEDULER_TOOLS = [
    types.FunctionDeclaration(
        name="check_frost_risk",
        description="Проверить риск заморозков для координат в ближайшие 48 часов",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "lat": types.Schema(type=types.Type.NUMBER),
                "lon": types.Schema(type=types.Type.NUMBER),
                "threshold_temp": types.Schema(type=types.Type.NUMBER, description="Критическая температура °C"),
            },
            required=["lat", "lon"]
        )
    ),
    types.FunctionDeclaration(
        name="generate_daily_agro_report",
        description="Сгенерировать ежедневную сводку агроиндексов для пользователя",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "user_id": types.Schema(type=types.Type.INTEGER),
                "report_date": types.Schema(type=types.Type.STRING),
            },
            required=["user_id"]
        )
    ),
    types.FunctionDeclaration(
        name="send_telegram_notification",
        description="Отправить уведомление пользователю в Telegram",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "user_id": types.Schema(type=types.Type.INTEGER),
                "message": types.Schema(type=types.Type.STRING),
                "priority": types.Schema(
                    type=types.Type.STRING,
                    description="urgent / normal / info"
                ),
            },
            required=["user_id", "message"]
        )
    ),
]

SCHEDULER_AGENT_INSTRUCTION = """
Ты — система мониторинга и уведомлений для фермеров.
Задача — своевременно предупреждать о критических агрономических событиях.

Приоритеты уведомлений:
- URGENT: заморозки < -2°C в ближайшие 48ч, экстремальные осадки, градобой
- NORMAL: оптимальные сроки посева/уборки, смена фаз вегетации
- INFO: ежедневные отчёты ГТК/GDD, еженедельные прогнозы

Формат алертов: краткий, конкретный, с практическими действиями.
Максимум 200 символов для urgent, 500 для normal, 1000 для daily report.
"""
```

---

## 📁 Структура файлов агентов

```
src/
├── agents/
│   ├── __init__.py
│   ├── orchestrator_agent.py      # Главный оркестратор
│   ├── data_collection_agent.py   # Сбор климатических/спутниковых данных
│   ├── rag_advisor_agent.py       # RAG консультации по агрономии
│   ├── forecast_agent.py          # ML-прогноз и рекомендации культур
│   ├── scheduler_agent.py         # Алерты и ежедневные отчёты
│   └── base_agent.py              # Базовый класс агента
├── tools/
│   ├── __init__.py
│   ├── climate_tools.py           # ERA5, Open-Meteo API
│   ├── satellite_tools.py         # Google Earth Engine tools
│   ├── soil_tools.py              # SoilGrids API tools
│   ├── ml_tools.py                # Random Forest inference
│   ├── rag_tools.py               # ChromaDB search tools
│   └── notification_tools.py     # Telegram Bot API tools
└── config/
    └── agent_config.py            # Конфигурация всех агентов
```

---

## ⚙️ Конфигурация (`src/config/agent_config.py`)

```python
import os
from dataclasses import dataclass

@dataclass
class AgentConfig:
    """Конфигурация мультиагентной системы Gemini"""
    
    # API ключи
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    
    # Модели
    orchestrator_model: str = "gemini-2.5-pro"
    worker_model: str = "gemini-2.0-flash"
    embedding_model: str = "text-embedding-004"
    
    # Параметры генерации
    temperature: float = 0.3           # Детерминированность для агрономии
    max_output_tokens: int = 2048
    
    # Таймауты (секунды)
    agent_timeout: int = 30
    tool_timeout: int = 15
    
    # Ограничения
    max_retries: int = 3
    rate_limit_rpm: int = 60           # Запросов в минуту
    
    # RAG настройки
    chroma_db_path: str = "./data/chroma_db"
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.7
    
    # Планировщик
    frost_alert_hours_ahead: int = 48
    daily_report_time: str = "07:00"   # Время ежедневного отчёта (UTC+3)

AGENT_CONFIG = AgentConfig()
```

---

## 🔄 Пример Flow: Запрос рекомендаций по культурам

```
Пользователь → /forecast + геолокация
    │
    ▼
OrchestratorAgent (принимает запрос)
    │
    ├─── DataCollectionAgent
    │        ├── fetch_era5_climate_data(lat, lon)
    │        ├── fetch_satellite_ndvi(lat, lon)
    │        ├── fetch_soil_data(lat, lon)
    │        └── calculate_agro_indices(climate_data)
    │               └─► возвращает: {gdd: 1240, gtc: 1.3, ndvi: 0.62, ph: 6.8}
    │
    ├─── ForecastAgent (получает данные от DataAgent)
    │        ├── run_ml_crop_forecast(feature_vector)
    │        ├── analyze_crop_risks(crops, weather)
    │        └── get_market_crop_prices(region, crops)
    │               └─► возвращает: [{crop: "пшеница", score: 87, risks: [...]}, ...]
    │
    └─── OrchestratorAgent (агрегирует результаты)
             └─► Формирует финальный ответ в Telegram Markdown
```

---

## 🛠 Интеграция с существующим кодом

### Подключение в Telegram handlers (`src/bot/handlers.py`)

```python
from src.agents.orchestrator_agent import OrchestratorAgent

# Инициализация агента (один раз при старте бота)
orchestrator = OrchestratorAgent(config=AGENT_CONFIG)

@router.message(Command("forecast"))
async def handle_forecast(message: Message, state: FSMContext):
    """Обработчик запроса прогноза культур через агентную систему"""
    user_data = await state.get_data()
    lat = user_data.get("lat")
    lon = user_data.get("lon")
    
    await message.answer("🔄 Анализирую данные поля...")
    
    # Вызов оркестратора
    result = await orchestrator.process_request(
        request_type="crop_forecast",
        user_id=message.from_user.id,
        params={"lat": lat, "lon": lon}
    )
    
    await message.answer(result.formatted_response, parse_mode="Markdown")
```

### Переменные окружения (добавить в `.env`)

```bash
# Google Gemini
GEMINI_API_KEY=your_gemini_api_key_here

# Опционально — fallback LLM
OPENROUTER_API_KEY=sk-or-v1-...
GROQ_API_KEY=gsk_...
```

---

## 📦 Зависимости (добавить в `requirements.txt`)

```
google-genai>=1.0.0          # Google Gemini SDK (новый unified SDK)
```

---

## 🗺 Roadmap реализации агентов

### Фаза 1 — Базовая интеграция (приоритет: ВЫСОКИЙ)
- [ ] `base_agent.py` — базовый класс с retry логикой и логированием
- [ ] `data_collection_agent.py` — заменяет прямые вызовы API в `src/api/`
- [ ] `forecast_agent.py` — обёртка над существующей RF-моделью

### Фаза 2 — RAG и консультации (приоритет: ВЫСОКИЙ)
- [ ] `rag_advisor_agent.py` — интеграция с существующим ChromaDB
- [ ] Обновить `src/knowledge/indexer.py` — использовать `text-embedding-004`
- [ ] Добавить обработчик `/ask` в Telegram handlers

### Фаза 3 — Оркестрация (приоритет: СРЕДНИЙ)
- [ ] `orchestrator_agent.py` — мультиагентный pipeline
- [ ] Миграция от прямых вызовов (Groq/OpenRouter) к Gemini
- [ ] A/B тестирование качества ответов

### Фаза 4 — Планировщик и алерты (приоритет: СРЕДНИЙ)
- [ ] `scheduler_agent.py` — интеграция с APScheduler
- [ ] AI-генерируемые персонализированные уведомления
- [ ] Персонализация отчётов на основе истории пользователя

### Фаза 5 — Продвинутые функции (приоритет: НИЗКИЙ)
- [ ] Multimodal: анализ фото посевов через Gemini Vision
- [ ] Голосовые запросы: Telegram Voice → Gemini STT
- [ ] Прогноз с доверительными интервалами + объяснимый AI (XAI)
- [ ] Интеграция с маркетплейсами (цены удобрений, семян)

---

## 🔒 Безопасность и лучшие практики

```python
# Всегда валидировать входные координаты перед передачей агентам
def validate_coordinates(lat: float, lon: float) -> bool:
    """Валидация координат для предотвращения prompt injection через геоданные"""
    return -90 <= lat <= 90 and -180 <= lon <= 180

# Ограничение размера контекста для экономии токенов
MAX_CONTEXT_CHARS = 50_000  # ~12K токенов

# Логирование всех вызовов агентов (без персональных данных)
import logging
logger = logging.getLogger("agents")
# Логировать: тип запроса, время выполнения, успех/ошибка
# НЕ логировать: координаты, user_id, содержимое ответов
```

---

## 📊 Мониторинг агентов (Prometheus)

```python
from prometheus_client import Counter, Histogram

agent_requests_total = Counter(
    "gemini_agent_requests_total",
    "Количество запросов к агентам",
    ["agent_name", "request_type", "status"]
)

agent_latency_seconds = Histogram(
    "gemini_agent_latency_seconds",
    "Время выполнения агентов",
    ["agent_name"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

gemini_tokens_used = Counter(
    "gemini_tokens_total",
    "Использованные токены Gemini",
    ["agent_name", "token_type"]  # input / output
)
```

---

*Документ создан для проекта [crop_forecast_bot](https://github.com/f2re/crop_forecast_bot)*  
*Версия: 1.0.0 | Апрель 2026*
