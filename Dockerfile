# Multi-stage build для лучшего кэширования
FROM python:3.11-slim as base

# Устанавливаем системные зависимости один раз
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем только requirements.txt для кэширования pip install
COPY requirements.txt .

# Устанавливаем Python зависимости (кэшируется если requirements.txt не изменился)
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем Playwright (кэшируется отдельно)
RUN playwright install --with-deps

# Копируем остальные файлы (только если они изменились)
COPY . .

CMD ["python", "-m", "src.backup"]
