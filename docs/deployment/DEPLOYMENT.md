# Deployment Guide

## Production Deployment for Screenshot Annotation Platform

This guide covers deploying the complete full-stack application with WebSocket support.

---

## Architecture Overview

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  React Frontend │─────▶│  FastAPI Backend │─────▶│  PostgreSQL DB  │
│   (Vite Build)  │      │  + WebSockets    │      │                 │
└─────────────────┘      └──────────────────┘      └─────────────────┘
         │                        │
         │                        │
         ▼                        ▼
    Static Files            uvicorn ASGI
    (Nginx/CDN)            (+ WebSocket)
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+
- Nginx (for production)
- SSL certificate (Let's Encrypt recommended)
- Domain name

---

## Backend Deployment

### 1. Environment Configuration

Create `.env` file:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/screenshot_annotations

# Security
SECRET_KEY=your-super-secret-key-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# File Storage
UPLOAD_DIR=/var/www/screenshot-uploads

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4
```

### 2. Database Setup

```bash
# Create database
createdb screenshot_annotations

# Run migrations (if using Alembic)
alembic upgrade head

# Or initialize manually
python -c "from src.screenshot_processor.web.database import init_db; import asyncio; asyncio.run(init_db())"
```

### 3. Install Dependencies

```bash
cd /path/to/screen-scrape
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install uvicorn[standard] gunicorn
```

### 4. Create Admin User

```bash
python -c "
import asyncio
from src.screenshot_processor.web.database import get_db_session
from src.screenshot_processor.web.services.auth_service import create_user

async def create_admin():
    async for db in get_db_session():
        await create_user(db, 'admin', 'admin@yourdomain.com', 'secure-password', role='admin')
        print('Admin user created')
        break

asyncio.run(create_admin())
"
```

### 5. Run with Uvicorn (Development)

```bash
uvicorn src.screenshot_processor.web.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Run with Gunicorn (Production)

Create `gunicorn.conf.py`:

```python
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
keepalive = 5
timeout = 30
graceful_timeout = 10
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# Logging
accesslog = "/var/log/screenshot-api/access.log"
errorlog = "/var/log/screenshot-api/error.log"
loglevel = "info"
```

Start server:

```bash
gunicorn src.screenshot_processor.web.api.main:app -c gunicorn.conf.py
```

### 7. Systemd Service

Create `/etc/systemd/system/screenshot-api.service`:

```ini
[Unit]
Description=Screenshot Annotation API
After=network.target postgresql.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/screenshot-scrape
Environment="PATH=/var/www/screenshot-scrape/venv/bin"
ExecStart=/var/www/screenshot-scrape/venv/bin/gunicorn \
    src.screenshot_processor.web.api.main:app \
    -c gunicorn.conf.py
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable screenshot-api
sudo systemctl start screenshot-api
sudo systemctl status screenshot-api
```

---

## Frontend Deployment

### 1. Environment Configuration

Create `frontend/.env.production`:

```bash
VITE_API_URL=https://api.yourdomain.com
VITE_WS_URL=wss://api.yourdomain.com/api/ws
```

### 2. Build for Production

```bash
cd frontend
npm install
npm run build
```

This creates optimized static files in `frontend/dist/`.

### 3. Deploy Static Files

```bash
# Copy to web server directory
sudo cp -r dist/* /var/www/screenshot-frontend/

# Set permissions
sudo chown -R www-data:www-data /var/www/screenshot-frontend
sudo chmod -R 755 /var/www/screenshot-frontend
```

---

## Nginx Configuration

### Backend API + WebSocket

Create `/etc/nginx/sites-available/screenshot-api`:

```nginx
upstream screenshot_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name api.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';

    # API endpoints
    location / {
        proxy_pass http://screenshot_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CORS headers
        add_header 'Access-Control-Allow-Origin' 'https://yourdomain.com' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;

        if ($request_method = 'OPTIONS') {
            return 204;
        }
    }

    # WebSocket endpoint
    location /api/ws {
        proxy_pass http://screenshot_api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket timeouts
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    # File uploads
    client_max_body_size 50M;
}
```

### Frontend

Create `/etc/nginx/sites-available/screenshot-frontend`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    root /var/www/screenshot-frontend;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript
               application/x-javascript application/xml+rss
               application/javascript application/json;

    # Static assets caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
}
```

Enable sites:

```bash
sudo ln -s /etc/nginx/sites-available/screenshot-api /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/screenshot-frontend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx

# Obtain certificates
sudo certbot --nginx -d api.yourdomain.com
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal (already configured via cron/systemd timer)
sudo certbot renew --dry-run
```

---

## Database Backup

### Automated Backups

Create `/usr/local/bin/backup-screenshot-db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/screenshot-db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/screenshot_annotations_$TIMESTAMP.sql"

mkdir -p $BACKUP_DIR

pg_dump -U postgres screenshot_annotations > $BACKUP_FILE

# Compress
gzip $BACKUP_FILE

# Delete backups older than 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "Backup completed: ${BACKUP_FILE}.gz"
```

Add to crontab:

```bash
sudo crontab -e
# Add line:
0 2 * * * /usr/local/bin/backup-screenshot-db.sh
```

---

## Monitoring

### Application Monitoring

Install and configure:

```bash
pip install prometheus-client
```

Add to backend:

```python
from prometheus_client import Counter, Histogram, make_asgi_app

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests')
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency')

# Mount metrics endpoint
from fastapi import FastAPI
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

### Log Monitoring

Use `logrotate` for log management:

Create `/etc/logrotate.d/screenshot-api`:

```
/var/log/screenshot-api/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload screenshot-api > /dev/null 2>&1 || true
    endscript
}
```

---

## Health Checks

### Backend Health Endpoint

Already available at: `https://api.yourdomain.com/health`

### Uptime Monitoring

Use UptimeRobot, Pingdom, or custom script:

```bash
#!/bin/bash
HEALTH_URL="https://api.yourdomain.com/health"
ALERT_EMAIL="admin@yourdomain.com"

RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $RESPONSE != "200" ]; then
    echo "API health check failed with status $RESPONSE" | \
        mail -s "Screenshot API Down" $ALERT_EMAIL
fi
```

---

## Scaling Considerations

### Horizontal Scaling

1. **Load Balancer**: Use Nginx upstream with multiple backend servers
2. **Session Management**: Store sessions in Redis (not localStorage)
3. **WebSocket Sticky Sessions**: Enable IP hash in Nginx

### Database Scaling

1. **Connection Pooling**: Already configured via SQLAlchemy
2. **Read Replicas**: Direct read queries to replicas
3. **Indexing**: Ensure indexes on frequently queried columns

---

## Security Checklist

- [ ] Change default SECRET_KEY
- [ ] Use strong admin password
- [ ] Enable HTTPS only
- [ ] Configure CORS properly
- [ ] Set rate limiting (e.g., slowapi)
- [ ] Enable SQL injection protection (parameterized queries)
- [ ] Regular dependency updates (`pip list --outdated`)
- [ ] Database backups automated
- [ ] Monitor logs for suspicious activity
- [ ] Implement CSP headers
- [ ] Use environment variables for secrets (never commit)

---

## Troubleshooting

### WebSocket Connection Issues

**Symptom**: WebSocket fails to connect

**Check**:
1. Nginx WebSocket proxy configuration
2. Firewall allows WSS traffic
3. SSL certificate valid
4. Token authentication in query parameter

**Debug**:
```bash
# Test WebSocket directly
wscat -c wss://api.yourdomain.com/api/ws?token=YOUR_TOKEN
```

### Database Connection Errors

**Check**:
1. PostgreSQL service running: `sudo systemctl status postgresql`
2. DATABASE_URL correct in `.env`
3. Database user has permissions
4. Connection pool not exhausted

### High Memory Usage

**Solutions**:
1. Reduce gunicorn workers
2. Increase server RAM
3. Enable database query caching
4. Optimize SQLAlchemy queries (eager loading)

---

## Rollback Procedure

1. Stop service: `sudo systemctl stop screenshot-api`
2. Restore database: `psql screenshot_annotations < backup.sql`
3. Checkout previous code: `git checkout <previous-commit>`
4. Restart: `sudo systemctl start screenshot-api`

---

## Maintenance Windows

Recommended schedule:
- **Database maintenance**: Sunday 2-4 AM
- **Application updates**: Saturday 11 PM - 12 AM
- **Server reboots**: First Sunday of month, 3 AM

---

## Support

For issues or questions:
- **Documentation**: `/docs` API docs endpoint
- **Logs**: `/var/log/screenshot-api/`
- **Database**: Access via `psql screenshot_annotations`

---

## Post-Deployment Checklist

- [ ] Backend health check passes
- [ ] Frontend loads correctly
- [ ] WebSocket connects successfully
- [ ] User can register and login
- [ ] Screenshot upload works
- [ ] Annotation submission succeeds
- [ ] Real-time updates functioning
- [ ] Admin dashboard accessible
- [ ] CSV export works
- [ ] Backups running automatically
- [ ] Monitoring alerts configured
- [ ] SSL certificates valid
- [ ] DNS records correct
- [ ] CORS properly configured
