import sys
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Пути, за которыми нужно следить
WATCH_PATHS = ['.', './src', './config']

def run_bot():
    """Запускает бота в дочернем процессе."""
    # Запускаем бота через subprocess, чтобы он работал в своем собственном процессе
    process = subprocess.Popen([sys.executable, 'run_bot.py'])
    return process

class ChangeHandler(FileSystemEventHandler):
    """Обработчик событий файловой системы для перезапуска бота."""
    def __init__(self):
        self.process = run_bot()

    def on_any_event(self, event):
        # Реагируем только на изменения в .py файлах
        if event.is_directory or not event.src_path.endswith('.py'):
            return

        print(f"Обнаружено изменение в {event.src_path}, перезапускаю бота...", flush=True)
        self.process.terminate()
        self.process.wait()
        self.process = run_bot()

if __name__ == "__main__":
    # Если запуск с флагом --dev, включаем автоперезагрузку
    if '--dev' in sys.argv:
        print("Запуск в режиме разработки с автоперезагрузкой...", flush=True)
        event_handler = ChangeHandler()
        observer = Observer()
        for path in WATCH_PATHS:
            observer.schedule(event_handler, path, recursive=True)
        
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            event_handler.process.terminate()
            event_handler.process.wait()
        observer.join()
    else:
        # В обычном режиме просто запускаем run_bot.py
        # Это основной способ запуска для production
        try:
            subprocess.run([sys.executable, 'run_bot.py'])
        except KeyboardInterrupt:
            print("\nБот остановлен.")

