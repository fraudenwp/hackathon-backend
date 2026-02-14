#!/bin/bash

# VoiceAI Backend - Quick Start Script

set -e

echo "🚀 VoiceAI Backend - Starting Production Deployment"
echo "=================================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env and set all required values:"
    echo "   - Database credentials"
    echo "   - API keys (FAL, LiveKit)"
    echo "   - Security keys (SECRET_KEY, JWT_SECRET_KEY)"
    echo "   - Cloudflare R2 credentials"
    echo ""
    echo "Then run this script again."
    exit 1
fi

# Validate critical env vars
echo "🔍 Validating environment variables..."
source .env

if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL not set in .env"
    exit 1
fi

if [ -z "$FAL_API_KEY" ]; then
    echo "❌ FAL_API_KEY not set in .env"
    exit 1
fi

if [ "$SECRET_KEY" = "your_secret_key_here" ]; then
    echo "❌ SECRET_KEY not changed from default!"
    echo "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
    exit 1
fi

echo "✅ Environment validation passed"

# Build and start services
echo ""
echo "🏗️  Building Docker images..."
docker-compose down 2>/dev/null || true
docker-compose build --no-cache

echo ""
echo "🚀 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Run migrations
echo ""
echo "📊 Running database migrations..."
docker-compose exec -T web alembic upgrade head

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📍 Services:"
echo "   - API: http://localhost:8005"
echo "   - API Health: http://localhost:8005/health"
echo "   - API Docs: http://localhost:8005/docs"
echo "   - LiveKit: http://localhost:7880"
echo ""
echo "📊 Check status:"
echo "   docker-compose ps"
echo ""
echo "📝 View logs:"
echo "   docker-compose logs -f"
echo "   docker-compose logs -f web"
echo "   docker-compose logs -f worker"
echo ""
echo "🛑 Stop services:"
echo "   docker-compose down"
echo ""
