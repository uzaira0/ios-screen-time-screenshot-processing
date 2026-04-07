# Deployment Security Guide

This document outlines security best practices for deploying the iOS Screen Time Screenshot Processing application.

## Table of Contents

1. [GitHub Repository Security](#github-repository-security)
2. [Secret Management](#secret-management)
3. [Server Security](#server-security)
4. [Secret Rotation Procedures](#secret-rotation-procedures)
5. [Incident Response](#incident-response)
6. [Security Checklist](#security-checklist)

---

## GitHub Repository Security

### Branch Protection Rules

Configure branch protection on `main` to prevent unauthorized deployments:

1. Go to **Settings → Branches → Add rule**
2. Branch name pattern: `main`
3. Enable:
   - [x] Require a pull request before merging
   - [x] Require approvals (minimum 1)
   - [x] Dismiss stale pull request approvals when new commits are pushed
   - [x] Require status checks to pass before merging
   - [x] Require branches to be up to date before merging
   - [x] Do not allow bypassing the above settings

### Environment Protection

Create a protected environment for production deployments:

1. Go to **Settings → Environments → New environment**
2. Name: `production`
3. Configure:
   - [x] Required reviewers (add yourself and/or team members)
   - [x] Wait timer: 5 minutes (optional, gives time to cancel)
   - [x] Deployment branches: Selected branches → `main` only
4. Add environment secrets (not repository secrets):
   - `SERVER_HOST`
   - `SERVER_USER`
   - `SERVER_SSH_KEY`
   - `SERVER_PORT` (optional, defaults to 22)
   - `APP_URL`

### Actions Permissions

1. Go to **Settings → Actions → General**
2. Actions permissions: **Allow select actions and reusable workflows**
3. Allow actions created by GitHub: ✓
4. Fork pull request workflows: **Require approval for all outside collaborators**

---

## Secret Management

### GitHub Secrets Hierarchy

| Secret Type | Scope | Use Case |
|-------------|-------|----------|
| Environment secrets | Per-environment | Production credentials (SSH keys, server IPs) |
| Repository secrets | All workflows | Shared secrets (not recommended for prod) |
| Organization secrets | All repos | Org-wide secrets |

**Best Practice**: Use environment-level secrets for production to isolate access.

### Server-Side Secrets

These secrets live ONLY on the server in `/opt/ios-screen-time-screenshot-processing/docker/.env`:

- `SECRET_KEY` - Application secret for session signing
- `POSTGRES_PASSWORD` - Database password
- `UPLOAD_API_KEY` - API key for programmatic uploads
- `ADMIN_USERNAMES` - Comma-separated admin usernames

**Never commit `.env` to version control!**

### Generating Secure Secrets

```bash
# Generate SECRET_KEY (64 hex characters)
python -c "import secrets; print(secrets.token_hex(32))"

# Generate UPLOAD_API_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate POSTGRES_PASSWORD
python -c "import secrets; print(secrets.token_urlsafe(24))"

# Generate SSH key pair (for GitHub Actions → Server)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy_key
```

---

## Server Security

### SSH Configuration

1. **Use key-based authentication only**:
   ```bash
   # /etc/ssh/sshd_config
   PasswordAuthentication no
   PubkeyAuthentication yes
   PermitRootLogin no
   ```

2. **Create dedicated deploy user**:
   ```bash
   useradd -m -s /bin/bash deploy
   usermod -aG docker deploy
   mkdir -p /home/deploy/.ssh
   # Add GitHub Actions public key to authorized_keys
   ```

3. **Limit deploy user permissions**:
   - Only access to `/opt/ios-screen-time-screenshot-processing/`
   - Docker group membership (to run docker commands)
   - No sudo access (or limited sudo for specific commands)

### Firewall Configuration

```bash
# Allow only necessary ports
firewall-cmd --permanent --add-port=22/tcp    # SSH
firewall-cmd --permanent --add-port=80/tcp    # HTTP
firewall-cmd --permanent --add-port=443/tcp   # HTTPS
firewall-cmd --reload
```

### Docker Security

1. **Don't run containers as root** (already configured in Dockerfiles)
2. **Use read-only filesystems where possible**
3. **Limit container resources** (memory, CPU)
4. **Keep images updated** - Rebuild regularly to get security patches

---

## Secret Rotation Procedures

### SSH Key Rotation (Every 90 Days)

1. **On server** - Generate new key pair:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions-deploy-$(date +%Y%m%d)" -f ~/.ssh/new_deploy_key
   ```

2. **Add new public key** to `/home/deploy/.ssh/authorized_keys`

3. **Update GitHub secret**:
   - Go to Settings → Environments → production → Secrets
   - Update `SERVER_SSH_KEY` with new private key

4. **Test deployment** with manual workflow trigger

5. **Remove old public key** from server's `authorized_keys`

### Database Password Rotation

1. **Stop application containers**:
   ```bash
   cd /opt/ios-screen-time-screenshot-processing/docker
   docker compose stop backend celery-worker
   ```

2. **Update PostgreSQL password**:
   ```bash
   docker compose exec postgres psql -U screenshot -c "ALTER USER screenshot PASSWORD 'new_password';"
   ```

3. **Update `.env` file** with new password (both `POSTGRES_PASSWORD` and `DATABASE_URL`)

4. **Restart containers**:
   ```bash
   docker compose up -d
   ```

### Application Secret Key Rotation

**Warning**: Rotating `SECRET_KEY` will invalidate all existing sessions.

1. Update `SECRET_KEY` in `.env`
2. Restart backend container
3. Users will need to re-authenticate

---

## Incident Response

### Suspected Compromise

1. **Immediately**:
   - Revoke compromised credentials
   - Rotate all secrets (SSH keys, passwords, API keys)
   - Review GitHub audit logs (Settings → Logs → Security log)
   - Check server access logs (`/var/log/secure`, `/var/log/auth.log`)

2. **Investigation**:
   - Review recent deployments
   - Check for unauthorized commits
   - Audit container logs: `docker compose logs --since 24h`

3. **Recovery**:
   - Deploy from known-good commit
   - Restore database from backup if needed
   - Document incident and lessons learned

### Failed Deployment Recovery

1. **Check logs**:
   ```bash
   cat /opt/ios-screen-time-screenshot-processing/logs/deploy.log
   docker compose logs --tail 100
   ```

2. **Rollback** to previous image:
   ```bash
   export IMAGE_TAG=previous_commit_sha
   ./scripts/deploy.sh
   ```

3. **If containers won't start**:
   ```bash
   docker compose down
   docker compose up -d
   ```

---

## Security Checklist

### Before First Deployment

- [ ] Repository is private
- [ ] Branch protection enabled on `main`
- [ ] GitHub environment `production` created with protection rules
- [ ] Environment secrets configured (not repo secrets)
- [ ] SSH key generated specifically for deployments
- [ ] Server firewall configured
- [ ] Deploy user created with minimal permissions
- [ ] `.env` file configured on server (not in repo)

### Regular Security Tasks

| Task | Frequency |
|------|-----------|
| Rotate SSH keys | Every 90 days |
| Review GitHub audit logs | Monthly |
| Update Docker base images | Monthly |
| Review access permissions | Quarterly |
| Test backup restoration | Quarterly |
| Rotate database password | Annually (or after personnel changes) |

### After Personnel Changes

- [ ] Remove their GitHub access
- [ ] Remove their server access
- [ ] Rotate all shared secrets
- [ ] Review recent audit logs

---

## Additional Resources

- [GitHub Actions Security Hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)
- [OWASP Security Checklist](https://owasp.org/www-project-web-security-testing-guide/)
