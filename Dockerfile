FROM python:3.12-slim

# Не создавать .pyc, не буферизировать stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Системные зависимости для сборки колёс (PyMySQL чистый Python, но на всякий)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Сначала зависимости — чтобы кеш слоя работал при правках кода
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Затем код
COPY . .

EXPOSE 5000

# По умолчанию — веб-приложение. Для collector команда переопределяется в compose.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]