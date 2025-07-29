FROM python:3.11-slim

# Install dependencies for Playwright
RUN apt-get update \ 
    && apt-get install -y --no-install-recommends \ 
       curl gnupg build-essential \ 
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps

COPY src ./src

CMD ["python", "-m", "src.backup"]
