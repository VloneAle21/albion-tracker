"""Lee la configuración del archivo .env (ver .env.example)."""

import os

from dotenv import load_dotenv

load_dotenv()

ALBION_SERVIDOR = os.getenv("ALBION_SERVIDOR", "europa")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_BD = os.getenv("MONGO_BD", "albion_tracker")
WORKER_MINUTOS = int(os.getenv("WORKER_MINUTOS", "10"))

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "tracker")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_BD = os.getenv("MYSQL_BD", "albion_tracker")
