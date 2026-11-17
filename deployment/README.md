# Smart AI Gateway — Production Deployment Guide

This directory contains the production deployment assets, container specifications, reverse proxy configs, and automated deployment scripts for **Smart AI Gateway**.

---

## 1. Quick Start: Automated Deployment

### Windows (PowerShell):
```powershell
.\deployment\deploy.ps1
```

### Linux / macOS:
```bash
chmod +x ./deployment/deploy.sh
./deployment/deploy.sh
```

The script automatically detects whether Docker is active:
- **With Docker**: Builds and starts the containerized service (`docker compose up -d`).
- **Without Docker**: Spawns a production Uvicorn background server and runs health checks.

---

## 2. Docker Compose Deployment

To build and run directly with Docker Compose:

```bash
# Single container gateway
docker compose -f deployment/docker-compose.yml up -d --build

# Full production stack (Gateway + PostgreSQL + Redis + Nginx TLS ingress)
docker compose -f docker-compose.prod.yml up -d --build
```

### Verifying Service Health:
- **Liveness probe**: `http://localhost:8000/health/live`
- **Readiness probe**: `http://localhost:8000/health/ready`
- **Web Playground**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

## 3. Cloud Platform Deployment (Render, Cloud Run, AWS)

### Render Deployment (`render.yaml`):
The repository includes a ready-to-deploy `render.yaml` blueprint:
1. Connect this GitHub repository to [Render.com](https://render.com).
2. Render detects `render.yaml` and deploys the web service automatically.
3. Configure your `GATEWAY_API_KEY` and model keys in the Render Dashboard environment settings.

---

## 4. Reverse Proxy & SSL Configuration (`nginx.conf`)

For custom VPS or Kubernetes ingress:
- Pre-configured Nginx reverse proxy with SSL termination, HTTP/2, connection pooling, and rate limiting (100 req/min with burst=20).
- Drop your TLS certificates into `deployment/certs/fullchain.pem` and `deployment/certs/privkey.pem`.
