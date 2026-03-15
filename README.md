# Export/Import API - Production Ready Implementation

## Overview

This is a secure, scalable async API for handling long-running export and import operations (>10 minutes, 1-100MB files).

### Architecture

```
┌─────────────┐
│   Client    │ (React/JavaScript)
└──────┬──────┘
       │ HTTPS
       ▼
┌──────────────────────┐
│   Nginx (Port 8080)  │ Rate limiting, security headers
└──────┬───────────────┘
       │
       ▼
┌─────────────────────┐
│  FastAPI (8000)     │ Validation, auth, status tracking
└──────┬──────────────┘
       │
    ┌──┴──┬──────┬─────────┐
    ▼     ▼      ▼         ▼
┌───────┐┌────┐┌───────┐┌──────┐
│Redis  ││  DB││MinIO  ││Celery│
│Queue  ││    ││Storage││Worker│✕3
└───────┘└────┘└───────┘└──────┘
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### Setup

1. **Clone and configure:**
   ```bash
   cd aidge_ai
   cp .env.example .env
   # Edit .env with your secure secrets
   ```

2. **Initialize database:**
   ```bash
   docker-compose down -v  # Clean start
   docker-compose up -d postgres redis minio minio-init
   sleep 5
   docker-compose exec api python /app/init_db.py
   ```

3. **Start all services:**
   ```bash
   docker-compose up -d
   ```

4. **Verify health:**
   ```bash
   curl http://localhost:8080/health
   ```

### Get Started

1. **Check API documentation:**
   - OpenAPI/Swagger: http://localhost:8080/docs
   - ReDoc: http://localhost:8080/redoc

2. **Get API key from logs:**
   ```bash
   docker-compose logs api | grep "API Key"
   ```

3. **Test export endpoint:**
   ```bash
   curl -X POST http://localhost:8080/api/v1/exports \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"format": "json"}'
   ```

## Security Features

### ✅ Authentication
- **API Key based** - Each customer has unique API keys
- **Database validation** - Keys stored with SHA256 hash
- **Expiration support** - Keys can expire automatically
- **Rate limiting** - Per-key tracking

### ✅ Authorization
- **Customer isolation** - Users can only access their own jobs
- **Multi-tenancy** - Complete data separation
- **Audit logging** - All requests logged with customer context

### ✅ Data Protection
- **Input validation** - Pydantic models validate all inputs
- **File size limits** - Max 100MB per upload
- **Type validation** - Only json/csv/xml formats allowed
- **SQL injection protection** - SQLAlchemy ORM prevents attacks

### ✅ Network Security
- **CORS** - Only whitelisted origins allowed
- **Security headers** - X-Frame-Options, X-Content-Type-Options, etc.
- **HTTPS ready** - Configured for TLS (nginx)
- **Rate limiting** - Per-IP request throttling

### ✅ Secrets Management
- **Environment variables** - No hardcoded credentials
- **.env files** - Git-ignored, use .env.example as template
- **Secure defaults** - Production requires strong passwords

## API Endpoints

### Health Check
```bash
GET /health
# No authentication required
# Response: {"status": "healthy", "version": "1.0.0"}
```

### Export Operations

**Create Export Job:**
```http
POST /api/v1/exports
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "format": "json",              # Required: json, csv, or xml
  "filters": {                   # Optional
    "date_from": "2024-01-01",
    "user_id": "123"
  }
}

Response (202):
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2024-03-13T10:30:00"
}
```

**Check Export Status:**
```http
GET /api/v1/exports/{job_id}
Authorization: Bearer {api_key}

Response (200):
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",        # pending, processing, completed, failed
  "progress": 45,                # 0-100%
  "created_at": "2024-03-13T10:30:00",
  "started_at": "2024-03-13T10:30:05",
  "completed_at": null,
  "error_message": null,
  "file_size": null
}
```

**Download Export File:**
```http
GET /api/v1/exports/{job_id}/download
Authorization: Bearer {api_key}

Response (200):
{
  "download_url": "http://minio:9000/exports/550e8400...?X-Amz-Signature=...",
  "expires_in_seconds": 3600
}
```

### Import Operations

**Upload Import File:**
```http
POST /api/v1/imports
Authorization: Bearer {api_key}
Content-Type: multipart/form-data

file: <binary file, max 100MB>
format: json|csv|xml

Response (202):
{
  "job_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "pending",
  "created_at": "2024-03-13T10:35:00"
}
```

**Check Import Status:**
```http
GET /api/v1/imports/{job_id}
Authorization: Bearer {api_key}

Response (200):
{
  "job_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "completed",
  "progress": 100,
  "created_at": "2024-03-13T10:35:00",
  "started_at": "2024-03-13T10:35:01",
  "completed_at": "2024-03-13T10:37:42",
  "error_message": null,
  "records_imported": 5000
}
```

## Load Handling

The system scales horizontally for high load:

### Current Configuration
- **3 Worker instances** - Process 3 jobs in parallel
- **Rate limiting** - 100 requests/minute per IP
- **Job timeout** - 10 minutes per job
- **Max file size** - 100MB per upload
- **Connection pooling** - 20 DB connections + 40 overflow

### Scale for Higher Load

**Option 1: Increase workers (Docker Compose)**
```yaml
worker:
  deploy:
    replicas: 10  # Increase from 3 to 10
```

**Option 2: Kubernetes**
```yaml
replicas: 10
resources:
  limits:
    cpu: "2"
    memory: "4Gi"
```

### Monitoring Load

```bash
# Check queue depth
redis-cli LLEN celery

# Monitor worker activity
docker-compose logs worker -f

# Database connections
docker-compose exec postgres psql -U export -d exports \
  -c "SELECT count(*) FROM pg_stat_activity;"

# Redis memory usage
redis-cli INFO memory
```

## Performance Tuning

### For Large Files (>50MB)

1. **Increase timeouts:**
   ```yaml
   # docker-compose.yaml
   environment:
     PROXY_TIMEOUT: 900  # 15 minutes
   ```

2. **Add more workers:**
   ```yaml
   worker:
     replicas: 5
   ```

3. **Stream large downloads:**
   - API already supports streaming responses
   - Files delivered in 8KB chunks

### For High Concurrency

1. **Increase database pool:**
   ```python
   # database.py
   pool_size=50
   max_overflow=100
   ```

2. **Increase Redis memory:**
   ```yaml
   redis:
     command: redis-server --maxmemory 2gb
   ```

3. **Enable nginx caching:**
   ```nginx
   proxy_cache_path /tmp/cache levels=1:2 keys_zone=api_cache:10m;
   proxy_cache api_cache;
   ```

## Error Handling

### Common Error Codes

| Code | Reason | Solution |
|------|--------|----------|
| 401 | Invalid/missing API key | Check Authorization header |
| 403 | API key expired | Generate new key |
| 404 | Job not found | Check job_id |
| 413 | File too large | Keep under 100MB |
| 429 | Rate limit exceeded | Wait before retrying |
| 500 | Server error | Check logs, retry later |

### Retry Strategy

```python
# Recommended client-side retry logic
import time
import random

def export_with_retry(api_key, format, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "http://localhost:8080/api/v1/exports",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"format": format}
            )
            if response.status_code == 429:
                # Rate limited - exponential backoff
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait_time)
                continue
            return response
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
```

## Monitoring & Observability

### Logging

All requests are logged with:
- Customer ID
- Job ID
- Action performed
- Timestamp
- Error details (if any)

```bash
# View API logs
docker-compose logs api -f

# View worker logs
docker-compose logs worker -f

# Search logs
docker-compose logs | grep "ERROR"
```

### Health Checks

```bash
# API health
curl http://localhost:8080/health

# Database
docker-compose exec postgres pg_isready

# Redis
docker-compose exec redis redis-cli ping

# MinIO
curl http://localhost:9000/minio/health/live
```

### Metrics Collection

Enabled via Prometheus (optional):

```python
# Add to main.py
from prometheus_client import Counter, Gauge

export_jobs = Counter('export_jobs_total', 'Total export jobs')
queue_depth = Gauge('celery_queue_depth', 'Queue depth')
```

## Testing

### Load Testing

```bash
python -m pip install locust

# Create locustfile.py (see examples/)
locust -f locustfile.py --host=http://localhost:8080
```

### Manual Testing

```bash
# 1. Get API key
API_KEY=$(docker-compose logs api | grep "API Key" | tail -1 | awk '{print $NF}')

# 2. Create export
JOB_ID=$(curl -s -X POST http://localhost:8080/api/v1/exports \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"format":"json"}' | jq -r '.job_id')

# 3. Check status in loop
for i in {1..30}; do
  curl -s -X GET "http://localhost:8080/api/v1/exports/$JOB_ID" \
    -H "Authorization: Bearer $API_KEY" | jq '.status, .progress'
  sleep 1
done

# 4. Download when complete
curl -s -X GET "http://localhost:8080/api/v1/exports/$JOB_ID/download" \
  -H "Authorization: Bearer $API_KEY" | jq '.download_url'
```

## Production Deployment

### Prerequisites
- Kubernetes cluster (recommended)
- SSL certificates
- Secrets management (Vault, AWS Secrets Manager)
- Monitoring (Prometheus + Grafana)

### Environment Variables
```bash
# Security
POSTGRES_PASSWORD=<use-strong-password>
MINIO_ROOT_PASSWORD=<use-strong-password>
REDIS_PASSWORD=<use-strong-password>

# Network
ALLOWED_ORIGINS=https://yourdomain.com
ENVIRONMENT=production

# Scaling
WORKER_CONCURRENCY=8
DATABASE_POOL_SIZE=30
```

### Kubernetes Example
```bash
# Deploy with Helm
helm install aidge-api ./helm-chart \
  --set environment=production \
  --set workers.replicas=10 \
  --set ingress.host=api.yourdomain.com
```

## Troubleshooting

### Queue Not Processing

```bash
# Check workers
docker-compose ps worker

# Check Redis connectivity
docker-compose exec worker redis-cli -h redis ping

# View worker logs
docker-compose logs worker --tail 50
```

### Database Connection Errors

```bash
# Check database
docker-compose exec postgres psql -U export -l

# Check pool usage
docker-compose exec api python -c \
  "from database import engine; print(engine.pool.checkedout())"
```

### MinIO Upload Failures

```bash
# Check buckets
docker-compose exec minio-init mc ls minio

# Check bucket permissions
docker-compose exec minio-init mc policy get minio/exports
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

MIT License - See [LICENSE](LICENSE)
