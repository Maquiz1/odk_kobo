#!/bin/bash

# Ensure script stops on error
set -e

echo "Starting Deployment for RTIS on Hostinger..."

# Build and start the containers
echo "Bringing up Docker containers for RTIS..."
docker compose up --build -d

echo "Waiting for PostgreSQL database to initialize..."
sleep 5

# Run migrations
echo "Running database migrations..."
docker compose exec web python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
docker compose exec web python manage.py collectstatic --noinput

# Seed roles
echo "Seeding initial roles..."
docker compose exec web python manage.py setup_roles

echo "RTIS Deployment completed successfully! The app is running on port 8001."
