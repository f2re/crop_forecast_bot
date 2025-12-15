#!/usr/bin/env python3
"""
Скрипт для быстрого обучения базовой ML модели для рекомендации культур
Генерирует синтетические данные для старта
"""
import os
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib

# Создаем директории
os.makedirs('models', exist_ok=True)
os.makedirs('data/training', exist_ok=True)

print("="*60)
print("ОБУЧЕНИЕ БАЗОВОЙ МОДЕЛИ CROP FORECAST BOT")
print("="*60)
print()

# Определяем культуры
CROPS = {
    0: 'wheat',      # Пшеница
    1: 'corn',       # Кукуруза
    2: 'sunflower',  # Подсолнечник
    3: 'soy',        # Соя
    4: 'barley',     # Ячмень
    5: 'rapeseed',   # Рапс
    6: 'potato',     # Картофель
    7: 'sugar_beet'  # Сахарная свекла
}

print("🌾 Культуры для обучения:")
for id, name in CROPS.items():
    print(f"  {id}: {name}")
print()

# Генерируем синтетические данные
print("📊 Генерация синтетических данных...")

np.random.seed(42)
n_samples = 5000

# Параметры каждой культуры (на основе crop_suitability.py)
CROP_PARAMS = {
    'wheat': {
        'T_avg': (15, 20), 'precip': (400, 700), 'gdd': (1600, 2000),
        'lai': (4, 6), 'ndvi': (0.6, 0.75), 'ph': (6.0, 7.5)
    },
    'corn': {
        'T_avg': (18, 25), 'precip': (500, 800), 'gdd': (2200, 2800),
        'lai': (5, 7), 'ndvi': (0.7, 0.85), 'ph': (5.5, 7.0)
    },
    'sunflower': {
        'T_avg': (20, 26), 'precip': (400, 600), 'gdd': (1800, 2300),
        'lai': (3, 5), 'ndvi': (0.65, 0.8), 'ph': (6.0, 7.5)
    },
    'soy': {
        'T_avg': (20, 28), 'precip': (500, 800), 'gdd': (2000, 2600),
        'lai': (4, 6), 'ndvi': (0.7, 0.85), 'ph': (6.0, 7.0)
    },
    'barley': {
        'T_avg': (12, 18), 'precip': (300, 600), 'gdd': (1400, 1800),
        'lai': (3, 5), 'ndvi': (0.55, 0.7), 'ph': (6.5, 7.5)
    },
    'rapeseed': {
        'T_avg': (12, 20), 'precip': (400, 700), 'gdd': (1600, 2100),
        'lai': (4, 6), 'ndvi': (0.65, 0.8), 'ph': (6.0, 7.5)
    },
    'potato': {
        'T_avg': (15, 22), 'precip': (500, 800), 'gdd': (1500, 2000),
        'lai': (4, 6), 'ndvi': (0.6, 0.75), 'ph': (5.0, 6.5)
    },
    'sugar_beet': {
        'T_avg': (15, 23), 'precip': (450, 750), 'gdd': (2000, 2600),
        'lai': (5, 7), 'ndvi': (0.65, 0.8), 'ph': (6.5, 7.5)
    }
}

# Генерируем данные
data = []
labels = []

for crop_name, crop_id in [('wheat', 0), ('corn', 1), ('sunflower', 2), ('soy', 3),
                            ('barley', 4), ('rapeseed', 5), ('potato', 6), ('sugar_beet', 7)]:
    params = CROP_PARAMS[crop_name]
    samples_per_crop = n_samples // 8

    for _ in range(samples_per_crop):
        # Генерируем значения с небольшим шумом
        T_avg = np.random.uniform(*params['T_avg']) + np.random.normal(0, 2)
        precip = np.random.uniform(*params['precip']) + np.random.normal(0, 50)
        gdd = np.random.uniform(*params['gdd']) + np.random.normal(0, 100)
        lai = np.random.uniform(*params['lai']) + np.random.normal(0, 0.5)
        ndvi = np.random.uniform(*params['ndvi']) + np.random.normal(0, 0.05)
        ph = np.random.uniform(*params['ph']) + np.random.normal(0, 0.3)

        # Дополнительные признаки
        gtk = np.random.uniform(0.8, 1.8)
        spi = np.random.uniform(-1.5, 1.5)
        soil_moisture = np.random.uniform(0.3, 0.9)
        frost_free_days = np.random.uniform(150, 250)

        # Ограничиваем значения разумными пределами
        T_avg = np.clip(T_avg, -10, 40)
        precip = np.clip(precip, 200, 1200)
        gdd = np.clip(gdd, 800, 3500)
        lai = np.clip(lai, 1, 8)
        ndvi = np.clip(ndvi, 0.3, 0.9)
        ph = np.clip(ph, 4.0, 8.5)

        data.append([
            T_avg, precip, gdd, lai, ndvi, ph,
            gtk, spi, soil_moisture, frost_free_days
        ])
        labels.append(crop_id)

# Создаем DataFrame
feature_names = [
    'temperature_avg', 'precipitation', 'gdd_cumulative', 'lai_avg',
    'ndvi_avg', 'ph', 'gtk', 'spi', 'soil_moisture', 'frost_free_days'
]

df = pd.DataFrame(data, columns=feature_names)
df['crop'] = labels

print(f"✓ Сгенерировано {len(df)} образцов")
print(f"  Признаков: {len(feature_names)}")
print(f"  Классов: {len(CROPS)}")
print()

# Сохраняем датасет
df.to_csv('data/training/synthetic_crop_data.csv', index=False)
print("✓ Данные сохранены: data/training/synthetic_crop_data.csv")
print()

# Разделяем на train/test
X = df[feature_names]
y = df['crop']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"📈 Разделение данных:")
print(f"  Train: {len(X_train)} образцов")
print(f"  Test:  {len(X_test)} образцов")
print()

# Обучаем модель
print("🤖 Обучение Random Forest...")
model = RandomForestClassifier(
    n_estimators=100,
    max_depth=15,
    min_samples_split=5,
    min_samples_leaf=2,
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)
print("✓ Модель обучена")
print()

# Оценка качества
train_score = model.score(X_train, y_train)
test_score = model.score(X_test, y_test)

print("📊 Результаты:")
print(f"  Train accuracy: {train_score:.3f}")
print(f"  Test accuracy:  {test_score:.3f}")
print()

# Важность признаков
feature_importance = pd.DataFrame({
    'feature': feature_names,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print("🔍 Важность признаков:")
for idx, row in feature_importance.iterrows():
    print(f"  {row['feature']:20s}: {row['importance']:.3f}")
print()

# Сохраняем модель
model_path = 'models/crop_rf_model.pkl'
joblib.dump(model, model_path)
print(f"✓ Модель сохранена: {model_path}")

# Сохраняем метаданные
metadata = {
    'crops': CROPS,
    'features': feature_names,
    'train_score': train_score,
    'test_score': test_score,
    'n_samples': len(df),
    'model_type': 'RandomForestClassifier'
}

metadata_path = 'models/crop_model_metadata.pkl'
joblib.dump(metadata, metadata_path)
print(f"✓ Метаданные сохранены: {metadata_path}")
print()

# Тестируем модель
print("🧪 Тестирование модели...")
print()

test_cases = [
    {"name": "Пшеница (средняя полоса)", "T_avg": 17, "precip": 550, "gdd": 1800,
     "lai": 5, "ndvi": 0.68, "ph": 6.8, "gtk": 1.2, "spi": 0.1, "soil_moisture": 0.65, "frost_free_days": 180},
    {"name": "Кукуруза (юг)", "T_avg": 22, "precip": 650, "gdd": 2500,
     "lai": 6, "ndvi": 0.78, "ph": 6.5, "gtk": 1.1, "spi": 0.3, "soil_moisture": 0.7, "frost_free_days": 200},
    {"name": "Подсолнечник (засушливый)", "T_avg": 23, "precip": 450, "gdd": 2100,
     "lai": 4, "ndvi": 0.72, "ph": 7.0, "gtk": 0.9, "spi": -0.5, "soil_moisture": 0.5, "frost_free_days": 190},
]

for test in test_cases:
    features = [[
        test['T_avg'], test['precip'], test['gdd'], test['lai'],
        test['ndvi'], test['ph'], test['gtk'], test['spi'],
        test['soil_moisture'], test['frost_free_days']
    ]]

    prediction = model.predict(features)[0]
    probabilities = model.predict_proba(features)[0]

    print(f"Случай: {test['name']}")
    print(f"  Предсказание: {CROPS[prediction]}")
    print(f"  Вероятности:")

    # Топ-3 культуры
    top_3_idx = np.argsort(probabilities)[::-1][:3]
    for idx in top_3_idx:
        print(f"    {CROPS[idx]:12s}: {probabilities[idx]:.1%}")
    print()

print("="*60)
print("✅ МОДЕЛЬ УСПЕШНО ОБУЧЕНА И ГОТОВА К ИСПОЛЬЗОВАНИЮ!")
print("="*60)
print()
print("📝 Следующие шаги:")
print("  1. Модель сохранена в models/crop_rf_model.pkl")
print("  2. Бот будет использовать ее для рекомендаций")
print("  3. Для улучшения модели добавьте реальные данные в:")
print("     data/training/synthetic_crop_data.csv")
print("  4. Повторно запустите этот скрипт для переобучения")
print()
print("🚀 Запустите бота: python run_bot.py")
print()
