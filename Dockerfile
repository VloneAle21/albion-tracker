# Una sola imagen para el worker y la web: cambia solo el comando (ver docker-compose.yml).
FROM python:3.12-slim

# Hora de Madrid dentro del contenedor (para los logs y las fechas de la web)
ENV TZ=Europe/Madrid \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Primero solo las dependencias: si no cambian, Docker reutiliza esta capa y el build es rápido.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tracker/ tracker/
COPY sql/esquema.sql sql/esquema.sql
COPY app.py .
COPY .streamlit/ .streamlit/

CMD ["python", "-m", "tracker.worker"]
