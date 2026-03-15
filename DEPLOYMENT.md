# Production Deployment Guide

## Pre-Deployment Checklist

### Security

- [ ] Change all default credentials in `.env`
  - [ ] POSTGRES_PASSWORD (Use 32+ character random string)
  - [ ] MINIO_ROOT_PASSWORD (Use 32+ character random string)
  - [ ] REDIS_PASSWORD (Add to .env if not set)

- [ ] Configure TLS/HTTPS
  - [ ] Obtain SSL certificates (Let's Encrypt recommended)
  - [ ] Place in nginx/certs/ directory
  - [ ] Update nginx.conf with SSL configuration
  - [ ] Force HTTPS redirect

- [ ] Update CORS
  - [ ] Set ALLOWED_ORIGINS to your domain
  - [ ] Remove localhost entries
  - [ ] Example: `ALLOWED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com`

- [ ] Enable database authentication
  - [ ] PostgreSQL strong passwords
  - [ ] Add database backups to backup plan

- [ ] MinIO security
  - [ ] Change root credentials
  - [ ] Set bucket policies to private
  - [ ] Enable encryption at rest

- [ ] API security
  - [ ] Review secret management (use Vault, AWS Secrets Manager, etc.)
  - [ ] Disable debug mode (ENV=production)
  - [ ] Enable request logging
  - [ ] Set up security monitoring

### Infrastructure

- [ ] Choose deployment platform
  - [ ] Kubernetes (recommended for scale)
  - [ ] Docker Compose on single server (for small deployments)
  - [ ] Managed services (AWS ECS, Google Cloud Run, etc.)

- [ ] Set up monitoring
  - [ ] Prometheus for metrics
  - [ ] Grafana for visualization
  - [ ] ELK stack or Datadog for logs

- [ ] Configure backups
  - [ ] PostgreSQL backups (daily minimum)
  - [ ] MinIO backups (to S3 or secondary storage)
  - [ ] Test restore procedures

- [ ] Set up alerting
  - [ ] Queue depth alerts
  - [ ] Error rate alerts
  - [ ] Disk space alerts
  - [ ] Memory alerts

- [ ] Load balancing
  - [ ] Set up load balancer (ALB, NLB, nginx, HAProxy)
  - [ ] Configure health checks
  - [ ] Enable auto-scaling

### Compliance

- [ ] Data protection
  - [ ] Enable encryption in transit (TLS)
  - [ ] Enable encryption at rest
  - [ ] Document data retention policies

- [ ] Audit logging
  - [ ] Enable request logging
  - [ ] Log retention policy
  - [ ] Audit trail for API key management

- [ ] Access control
  - [ ] RBAC for team members
  - [ ] API key rotation schedule
  - [ ] Document security procedures

---

## Deployment Options

### Option 1: Single Server (Docker Compose)

**Best for:** Small deployments, development, staging

**Prerequisites:**
- Ubuntu 20.04+ or similar
- Docker 20.10+
- Docker Compose 2.0+

**Steps:**

```bash
# 1. SSH to server
ssh ubuntu@your-server.com

# 2. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. Clone repository
git clone https://github.com/yourorg/aidge_ai.git
cd aidge_ai

# 4. Configure production environment
cp .env.example .env
# Edit .env with production credentials
nano .env

# 5. Start services
docker-compose -f docker-compose.yaml up -d

# 6. Verify health
curl http://localhost:8080/health

# 7. Initialize database
docker-compose exec api python /app/init_db.py

# 8. Extract API key
docker-compose logs api | grep "API Key"
```

**Scaling:**
```bash
# Scale workers to 10 instances
docker-compose up -d --scale worker=10

# View status
docker-compose ps
```

---

### Option 2: Kubernetes (Recommended for Production)

**Best for:** Large deployments, high availability, auto-scaling

**Prerequisites:**
- Kubernetes 1.20+
- kubectl configured
- Helm 3.0+

**Deployment:**

Create `helm/values-prod.yaml`:
```yaml
environment: production

api:
  replicas: 3
  resources:
    requests:
      cpu: 500m
      memory: 2Gi
    limits:
      cpu: 2
      memory: 4Gi

worker:
  replicas: 10
  resources:
    requests:
      cpu: 1
      memory: 2Gi
    limits:
      cpu: 2
      memory: 4Gi

postgres:
  persistence:
    size: 100Gi
  resources:
    requests:
      cpu: 1
      memory: 4Gi

redis:
  persistence:
    size: 50Gi

minio:
  persistence:
    size: 500Gi

ingress:
  enabled: true
  domain: api.yourdomain.com
  tls:
    enabled: true
    certIssuer: letsencrypt-prod

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
  targetCPUUtilization: 70
```

Deploy:
```bash
# 1. Create namespace
kubectl create namespace aidge

# 2. Create secrets
kubectl create secret generic aidge-secrets \
  --from-literal=postgres-password=YOUR_PASSWORD \
  --from-literal=minio-password=YOUR_PASSWORD \
  -n aidge

# 3. Deploy with Helm
helm install aidge ./helm-chart \
  --namespace aidge \
  --values helm/values-prod.yaml

# 4. Monitor deployment
kubectl get pods -n aidge
kubectl logs -n aidge deployment/aidge-api
```

---

### Option 3: AWS ECS (Fargate)

Create `ecs-task-definition.json`:
```json
{
  "family": "aidge-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "YOUR_ECR_REGISTRY/aidge-api:latest",
      "portMappings": [{
        "containerPort": 8000,
        "hostPort": 8000,
        "protocol": "tcp"
      }],
      "environment": [
        {
          "name": "DATABASE_URL",
          "value": "postgresql://export:${DB_PASSWORD}@${RDS_ENDPOINT}:5432/exports"
        }
      ],
      "secrets": [
        {
          "name": "POSTGRES_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:..."
        }
      ]
    }
  ]
}
```

Deploy:
```bash
# Push image to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ECR_REGISTRY
docker tag aidge-api:latest YOUR_ECR_REGISTRY/aidge-api:latest
docker push YOUR_ECR_REGISTRY/aidge-api:latest

# Register task definition
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json

# Create ECS service
aws ecs create-service \
  --cluster aidge-prod \
  --service-name aidge-api \
  --task-definition aidge-api:1 \
  --desired-count 3 \
  --load-balancers targetGroupArn=arn:aws:...
```

---

## Post-Deployment

### Verification

```bash
# 1. Health check
curl https://api.yourdomain.com/health

# 2. Check database
psql -h DB_HOST -U export -d exports -c "SELECT version();"

# 3. Test export endpoint
curl -X POST https://api.yourdomain.com/api/v1/exports \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"format":"json"}'

# 4. Monitor logs
docker logs $(docker ps -q -f "name=api")
```

### Monitoring Setup

**Prometheus Configuration:**
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'aidge-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'

  - job_name: 'postgres'
    static_configs:
      - targets: ['localhost:5432']

  - job_name: 'redis'
    static_configs:
      - targets: ['localhost:6379']
```

**Grafana Dashboard:**
- Job queue depth
- Worker utilization
- API response times
- Error rates
- Database connections
- Memory usage

---

## Maintenance

### Regular Tasks

**Daily:**
```bash
# Check health
curl https://api.yourdomain.com/health

# Monitor queue depth
redis-cli LLEN celery

# Review error logs
docker logs aidge-api 2>&1 | grep ERROR
```

**Weekly:**
```bash
# Backup database
pg_dump -h DB_HOST -U export exports > backup_$(date +%Y%m%d).sql

# Review performance metrics
# Check Grafana dashboards

# Verify backups are working
# Test restore procedure
```

**Monthly:**
```bash
# Rotate API keys
# Update secrets
# Review security logs
# Test disaster recovery
# Update dependencies
```

### Scaling UP

When queue depth increases:

```bash
# With Docker Compose
docker-compose up -d --scale worker=20

# With Kubernetes
kubectl scale deployment aidge-worker --replicas=20 -n aidge

# Check queue
redis-cli LLEN celery
```

### Disaster Recovery

```bash
# 1. Database backup restoration
psql -h NEW_HOST -U export exports < backup.sql

# 2. MinIO bucket restoration
# Use AWS S3 Cross-Region Replication or manual restore

# 3. Application redeployment
docker-compose up -d
# or
helm upgrade aidge ./helm-chart --namespace aidge
```

---

## Troubleshooting

### Workers Not Processing Jobs

```bash
# 1. Check Redis connection
redis-cli PING

# 2. Check worker logs
docker logs aidge-worker-1

# 3. Verify queue
redis-cli LLEN celery

# 4. Restart workers
docker-compose restart worker
```

### High Latency

```bash
# 1. Check database connections
docker exec postgres psql -U export -c \
  "SELECT count(*) FROM pg_stat_activity;"

# 2. Check Redis memory
redis-cli INFO memory

# 3. Check worker CPU
docker stats

# 4. Scale up
docker-compose up -d --scale worker=10
```

### API Key Errors

```bash
# Generate new key
docker-compose exec api python -c "
from database import SessionLocal, Customer, ApiKey
from auth import hash_key
import uuid
db = SessionLocal()
customer = db.query(Customer).first()
key = 'new_key_' + str(uuid.uuid4())
api_key = ApiKey(
    id=str(uuid.uuid4()),
    customer_id=customer.id,
    key_hash=hash_key(key)
)
db.add(api_key)
db.commit()
print(f'New key: {key}')
"
```

---

## Security Updates

### Update docker images

```bash
# Pull latest images
docker-compose pull

# Rebuild with latest base images
docker-compose build --pull

# Restart services
docker-compose up -d
```

### Update Python dependencies

```bash
# Update requirements
pip install --upgrade -r requirements.txt

# Rebuild Docker images
docker-compose build

# Restart
docker-compose up -d
```

---

## Performance Optimization

### Database

```sql
-- Add indexes for common queries
CREATE INDEX idx_export_customer_id ON export_jobs(customer_id);
CREATE INDEX idx_export_status ON export_jobs(status);
CREATE INDEX idx_import_customer_id ON import_jobs(customer_id);

-- Analyze query performance
EXPLAIN ANALYZE SELECT * FROM export_jobs WHERE customer_id = $1;
```

### Redis

```bash
# Monitor Redis
redis-cli MONITOR

# Clear old jobs
redis-cli FLUSHDB

# Adjust memory policy
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### MinIO

```bash
# Monitor bucket sizes
mc du minio/exports

# Enable compression
mc admin config set minio compression enable
```

---

## Cost Optimization

- Use auto-scaling to reduce costs during low traffic
- Archive old job records to cheaper storage
- Use regional replication for MinIO
- Implement database query caching
- Use CDN for file downloads

---

## Support & Escalation

1. Check logs: `docker logs servicename`
2. Review metrics: Prometheus/Grafana
3. Check system resources: `docker stats`
4. Review configuration: `.env` and docker-compose
5. Contact support if issues persist

---

## Rollback Procedure

If issues arise post-deployment:

```bash
# 1. Check current version
docker inspect aidge-api:latest | grep Version

# 2. Pull previous version
docker pull aidge-api:v1.0.0

# 3. Update docker-compose.yaml
# Change: image: aidge-api:latest
# To: image: aidge-api:v1.0.0

# 4. Restart
docker-compose down
docker-compose up -d

# 5. Verify
curl https://api.yourdomain.com/health
```

---

## Next Steps

1. Set up monitoring and alerting
2. Configure backup procedures
3. Document runbooks for your team
4. Schedule regular disaster recovery drills
5. Plan for capacity growth
