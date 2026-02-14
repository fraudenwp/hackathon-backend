# Production Deployment Guide

## Prerequisites

- Docker & Docker Compose installed
- PostgreSQL database (external or containerized)
- Domain name configured
- SSL certificates (Let's Encrypt recommended)

## Environment Setup

1. **Copy environment template:**
```bash
cp .env.example .env
```

2. **Configure environment variables:**

Edit `.env` and set all required values:

```bash
# Database - Use external PostgreSQL or configure in docker-compose
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# Security Keys - Generate new ones!
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
SECRET_KEY_ENCRYPTION=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# API Keys
FAL_API_KEY=your_fal_api_key  # From https://fal.ai/dashboard/keys
LIVEKIT_API_KEY=your_key      # From https://cloud.livekit.io/
LIVEKIT_API_SECRET=your_secret

# Cloudflare R2
R2_ACCESS_KEY_ID=your_key
R2_SECRET_ACCESS_KEY=your_secret
R2_BUCKET_NAME=your_bucket
```

## Deployment Steps

### 1. Build and Start Services

```bash
# Production mode
docker-compose up -d --build

# Check logs
docker-compose logs -f web
docker-compose logs -f worker
```

### 2. Run Database Migrations

```bash
docker-compose exec web alembic upgrade head
```

### 3. Verify Services

```bash
# Check service health
docker-compose ps

# Test API health endpoint
curl http://localhost:8005/health
```

## Architecture

```
┌─────────────────┐
│   Load Balancer │  (Nginx/Traefik)
└────────┬────────┘
         │
    ┌────┴────┐
    │   Web   │  (FastAPI - 4 workers)
    └────┬────┘
         │
    ┌────┴────────────────┬──────────────┐
    │                     │              │
┌───┴────┐         ┌─────┴─────┐   ┌───┴───────┐
│ Worker │         │  Valkey   │   │  LiveKit  │
│ (Taskiq)│         │  (Cache)  │   │  (Voice)  │
└────────┘         └───────────┘   └───────────┘
                         │
                    ┌────┴────┐
                    │PostgreSQL│
                    └─────────┘
```

## Services

- **web**: FastAPI application (Port 8005)
- **worker**: Background task processor (Taskiq)
- **valkey-worker**: Redis-compatible cache
- **LiveKit**: Voice/Video (via LiveKit Cloud - configured in .env)

## Database Migrations

### Create new migration:
```bash
docker-compose exec web alembic revision --autogenerate -m "description"
docker-compose exec web alembic upgrade head
```

### View migration history:
```bash
docker-compose exec web alembic history
docker-compose exec web alembic current
```

## Monitoring

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f worker
docker-compose logs -f livekit
```

### Resource Usage
```bash
docker stats
```

### Health Checks
```bash
# API health
curl http://localhost:8005/health

# LiveKit health
curl http://localhost:7880/
```

## Scaling

### Scale workers:
```bash
docker-compose up -d --scale worker=4
```

### Web workers (edit docker-compose.yml):
```yaml
web:
  command: uvicorn src:app --workers 8 --host 0.0.0.0 --port 8005
```

## Security Checklist

- [ ] All secret keys generated uniquely
- [ ] Database uses strong password
- [ ] SSL/TLS enabled (reverse proxy)
- [ ] Firewall configured (allow only necessary ports)
- [ ] Environment variables not committed to git
- [ ] CORS configured properly in production
- [ ] Rate limiting enabled
- [ ] Regular backups configured

## Backup & Restore

### Database Backup
```bash
# Backup
docker-compose exec -T db pg_dump -U postgres resai > backup.sql

# Restore
docker-compose exec -T db psql -U postgres resai < backup.sql
```

### Valkey Backup
```bash
docker-compose exec valkey-worker valkey-cli SAVE
docker cp $(docker-compose ps -q valkey-worker):/data/dump.rdb ./valkey-backup.rdb
```

## Troubleshooting

### Service won't start
```bash
docker-compose logs <service-name>
docker-compose down
docker-compose up -d --build
```

### Database connection issues
```bash
# Check database container
docker-compose exec db psql -U postgres -l

# Test connection from web
docker-compose exec web python -c "from src.models.database import db; print(db)"
```

### Worker not processing tasks
```bash
# Check worker logs
docker-compose logs -f worker

# Check Valkey connection
docker-compose exec valkey-worker valkey-cli ping
```

## Performance Tuning

### Web Service
- Increase workers: `--workers 8`
- Resource limits in docker-compose.yml
- Enable HTTP/2 in reverse proxy

### Database
- Connection pooling (already configured)
- Regular VACUUM and ANALYZE
- Index optimization

### Valkey
- Adjust maxmemory policy
- Monitor memory usage
- Use persistence if needed

## Updates

### Update application:
```bash
git pull
docker-compose down
docker-compose up -d --build
docker-compose exec web alembic upgrade head
```

### Update dependencies:
```bash
# Edit requirements.in
pip-compile --no-emit-index-url
docker-compose up -d --build
```

## Support

For issues, check:
- Application logs: `docker-compose logs`
- Health endpoints
- Database connectivity
- External API status (FAL, LiveKit)
