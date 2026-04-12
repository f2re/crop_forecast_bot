import csv
import random
from selenium import webdriver
# Импортируем опции для Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Список User-Agent для ротации
user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (X11; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0'
]

# Настраиваем опции для запуска Firefox
firefox_options = Options()
firefox_options.set_preference("general.useragent.override", random.choice(user_agents)) # Устанавливаем случайный User-Agent
firefox_options.add_argument('--headless')  # Запуск в фоновом режиме
firefox_options.add_argument('--disable-gpu')
firefox_options.add_argument('--no-sandbox')
firefox_options.add_argument("--width=1920")
firefox_options.add_argument("--height=1080")

# Инициализация драйвера для Firefox
browser = webdriver.Firefox(options=firefox_options)

try:
    url = 'https://agroserver.ru/top/'
    browser.get(url)

    # Ожидаем, пока таблица не станет доступна (максимум 15 секунд)
    wait = WebDriverWait(browser, 15)
    table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'table.top_table_4')))

    # Извлекаем данные
    data = []
    rows = table.find_elements(By.CSS_SELECTOR, 'tr')[1:] # Пропускаем заголовки

    for row in rows:
        cols = row.find_elements(By.TAG_NAME, 'td')
        if len(cols) >= 4:
            rank = cols[0].text.strip()
            title = cols[1].text.strip()
            visitors = cols[2].text.strip()
            views = cols[3].text.strip()
            data.append([rank, title, visitors, views])

    # Сохраняем результат в CSV
    with open('agroserver_stats_firefox.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Позиция', 'Название ресурса', 'Посетители', 'Просмотры'])
        writer.writerows(data)

    print("Данные успешно сохранены в файл agroserver_stats_firefox.csv")

except Exception as e:
    print(f"Произошла ошибка: {e}")

finally:
    # Обязательно закрываем браузер
    browser.quit()
