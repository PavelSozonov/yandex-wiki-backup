#!/bin/bash
echo "🏗️  Собираем базовый образ с Playwright (это займёт время, но только один раз)..."
docker build -f Dockerfile.base -t yandex-wiki-backup:base .

echo "✅ Базовый образ готов! Теперь можно использовать быструю сборку."
echo "💡 Используйте: docker compose -f docker-compose.fast.yaml up --build" 