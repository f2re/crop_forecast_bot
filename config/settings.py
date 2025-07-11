import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Учетные данные для Copernicus CDS API
CDS_API_URL = os.getenv("CDS_API_URL")
CDS_API_KEY = os.getenv("CDS_API_KEY")
