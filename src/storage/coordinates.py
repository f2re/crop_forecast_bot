import json
import os

DATA_FILE = "data/coordinates.json"

def save_coordinates(user_id, latitude, longitude):
    """Сохраняет координаты пользователя в JSON файл."""
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump({}, f)
    
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    
    data[str(user_id)] = {
        "latitude": latitude,
        "longitude": longitude
    }
    
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Координаты пользователя {user_id} сохранены: {latitude}, {longitude}")

def load_coordinates(user_id):
    """Загружает координаты пользователя из JSON файла."""
    if not os.path.exists(DATA_FILE):
        return None
    
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    
    return data.get(str(user_id))
