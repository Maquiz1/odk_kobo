#!/bin/bash

# Ensure script stops on error
set -e

echo "🚀 Starting Deployment for RTIS..."

# 1. Pull latest changes from git
echo "📥 Pulling latest changes from Git (develop branch)..."
git pull origin develop

# 2. Build and start containers
echo "⚙️ Bringing up Docker containers (building if changed)..."
docker compose up -d --build

# 3. Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL database to initialize..."
sleep 5

# 4. Run database migrations
echo "📦 Running database migrations..."
docker compose exec -T web python manage.py migrate --noinput

# 5. Collect static files
echo "🎨 Collecting static files..."
docker compose exec -T web python manage.py collectstatic --noinput

# 6. Seed roles
echo "🔑 Seeding initial roles..."
docker compose exec -T web python manage.py setup_roles

echo "✨ RTIS Deployment completed successfully! The app is running on port 8001."

