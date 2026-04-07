# Plan: HA Deployment with Ansible + Docker Compose

> **Status**: Draft - Stashed for future reference
>
> This plan was designed for multi-server HA deployment (RedHat + Windows) but determined to be too complex for current needs. Saved for potential future use.

## Overview

Automated deployment to RedHat + Windows 10/11 servers using:
- **Ansible** for configuration management and deployment orchestration
- **Docker Compose** for running identical Linux container stacks on both servers
- **GitHub Actions** for CI/CD (build images on push to main)
- **HAProxy + Keepalived** for load balancing and VIP failover
- **PostgreSQL streaming replication** for database HA
- **Lsyncd** for file synchronization

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Dev Machine (Windows + WSL)                   │
│                    Ansible control node - NO containers              │
└─────────────────────────────────────────────────────────────────────┘
                                    │ ansible-playbook
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                      ▼
┌─────────────────────┐                              ┌─────────────────────┐
│  RedHat Server      │                              │  Windows 10/11      │
│  (PRIMARY)          │                              │  (SECONDARY)        │
├─────────────────────┤                              ├─────────────────────┤
│ Keepalived (MASTER) │◄────── VRRP heartbeat ──────►│ Keepalived (BACKUP) │
│ HAProxy             │                              │ HAProxy             │
├─────────────────────┤                              ├─────────────────────┤
│ Docker (native)     │                              │ Docker Desktop      │
│ Linux containers:   │                              │ Linux containers    │
│ - Frontend          │                              │ (via WSL2):         │
│ - Backend           │                              │ - Frontend          │
│ - Celery            │                              │ - Backend           │
│ - Redis             │                              │ - Celery            │
│ - PostgreSQL (pri)  │───streaming replication─────►│ - Redis             │
│                     │                              │ - PostgreSQL (repl) │
├─────────────────────┤                              ├─────────────────────┤
│ /uploads (source)   │───────Lsyncd/rsync──────────►│ /uploads (mirror)   │
└─────────────────────┘                              └─────────────────────┘
                    │
                    ▼
           Virtual IP (VIP)
           Users connect here
```

## Directory Structure to Create

```
apps/screenshot-annotator/
├── ansible/
│   ├── ansible.cfg                    # Ansible configuration
│   ├── inventory/
│   │   ├── hosts.yml                  # Server inventory
│   │   └── group_vars/
│   │       ├── all.yml                # Shared variables
│   │       ├── primary.yml            # Primary server vars
│   │       └── secondary.yml          # Secondary server vars
│   ├── playbooks/
│   │   ├── site.yml                   # Main playbook (runs all)
│   │   ├── provision.yml              # Initial server setup
│   │   ├── deploy.yml                 # Deploy application
│   │   ├── rollback.yml               # Rollback to previous version
│   │   └── maintenance.yml            # Start/stop maintenance mode
│   ├── roles/
│   │   ├── common/                    # Shared setup (Docker, users, firewall)
│   │   ├── haproxy/                   # HAProxy configuration
│   │   ├── keepalived/                # Keepalived + VIP
│   │   ├── postgres/                  # PostgreSQL with replication
│   │   ├── redis/                     # Redis setup
│   │   ├── application/               # Backend + Frontend + Celery
│   │   └── lsyncd/                    # File synchronization
│   └── templates/
│       ├── docker-compose.ha.yml.j2   # Templated compose file
│       ├── haproxy.cfg.j2             # HAProxy config
│       ├── keepalived.conf.j2         # Keepalived config
│       └── .env.j2                    # Environment file
├── docker/
│   └── ha/                            # HA-specific configs (reference)
│       ├── postgres/
│       │   ├── postgresql.conf.primary
│       │   ├── postgresql.conf.replica
│       │   └── pg_hba.conf
│       └── scripts/
│           ├── failover.sh
│           └── health-check.sh
└── .github/
    └── workflows/
        └── deploy-ha.yml              # Build images, trigger Ansible
```

## Files to Create

### Phase 1: Ansible Infrastructure (12 files)

| File | Purpose |
|------|---------|
| `ansible/ansible.cfg` | Ansible settings (SSH, privilege escalation) |
| `ansible/inventory/hosts.yml` | Server inventory with groups |
| `ansible/inventory/group_vars/all.yml` | Shared variables (secrets, versions) |
| `ansible/inventory/group_vars/primary.yml` | Primary-specific vars |
| `ansible/inventory/group_vars/secondary.yml` | Secondary-specific vars |
| `ansible/playbooks/site.yml` | Main entry point |
| `ansible/playbooks/provision.yml` | Initial server setup |
| `ansible/playbooks/deploy.yml` | Application deployment |
| `ansible/roles/common/tasks/main.yml` | Docker install, firewall, users |
| `ansible/roles/common/handlers/main.yml` | Service restart handlers |
| `ansible/roles/common/tasks/docker-redhat.yml` | Docker on RedHat |
| `ansible/roles/common/tasks/docker-windows.yml` | Docker Desktop verification |

### Phase 2: HAProxy + Keepalived Roles (8 files)

| File | Purpose |
|------|---------|
| `ansible/roles/haproxy/tasks/main.yml` | Install and configure HAProxy |
| `ansible/roles/haproxy/templates/haproxy.cfg.j2` | HAProxy config template |
| `ansible/roles/haproxy/handlers/main.yml` | Reload HAProxy |
| `ansible/roles/keepalived/tasks/main.yml` | Install Keepalived |
| `ansible/roles/keepalived/templates/keepalived.conf.j2` | VRRP config |
| `ansible/roles/keepalived/templates/check_haproxy.sh.j2` | Health check |
| `ansible/roles/keepalived/handlers/main.yml` | Restart Keepalived |
| `ansible/roles/keepalived/tasks/windows.yml` | Keepalived in Docker for Windows |

### Phase 3: Database + Redis Roles (6 files)

| File | Purpose |
|------|---------|
| `ansible/roles/postgres/tasks/main.yml` | PostgreSQL with replication |
| `ansible/roles/postgres/tasks/primary.yml` | Primary setup (WAL, slots) |
| `ansible/roles/postgres/tasks/replica.yml` | Replica setup (pg_basebackup) |
| `ansible/roles/postgres/templates/postgresql.conf.j2` | PostgreSQL config |
| `ansible/roles/redis/tasks/main.yml` | Redis container setup |
| `ansible/roles/redis/templates/redis.conf.j2` | Redis config |

### Phase 4: Application Role (6 files)

| File | Purpose |
|------|---------|
| `ansible/roles/application/tasks/main.yml` | Deploy app containers |
| `ansible/roles/application/tasks/pull.yml` | Pull images from registry |
| `ansible/roles/application/tasks/migrate.yml` | Run DB migrations |
| `ansible/roles/application/templates/docker-compose.ha.yml.j2` | Compose template |
| `ansible/roles/application/templates/.env.j2` | Environment variables |
| `ansible/roles/application/handlers/main.yml` | Restart services |

### Phase 5: File Sync Role (3 files)

| File | Purpose |
|------|---------|
| `ansible/roles/lsyncd/tasks/main.yml` | Install and configure Lsyncd |
| `ansible/roles/lsyncd/templates/lsyncd.conf.lua.j2` | Sync config |
| `ansible/roles/lsyncd/tasks/ssh-keys.yml` | Setup SSH keys for rsync |

### Phase 6: GitHub Actions (1 file)

| File | Purpose |
|------|---------|
| `.github/workflows/deploy-ha.yml` | Build images, push to GHCR, trigger Ansible |

### Phase 7: Documentation (2 files)

| File | Purpose |
|------|---------|
| `ansible/README.md` | Setup and usage instructions |
| `docker/ha/FAILOVER.md` | Manual failover procedure |

## Total: 38 files

## Key Ansible Variables

```yaml
# ansible/inventory/group_vars/all.yml
---
app_name: screenshot-annotator
app_version: "{{ lookup('env', 'APP_VERSION') | default('latest') }}"
registry: ghcr.io/your-org

# Network
vip_address: 192.168.1.100
primary_ip: 192.168.1.101
secondary_ip: 192.168.1.102

# Secrets (use ansible-vault in production)
postgres_password: "{{ vault_postgres_password }}"
secret_key: "{{ vault_secret_key }}"
upload_api_key: "{{ vault_upload_api_key }}"

# Paths
app_dir: /opt/screenshot-annotator  # Linux
app_dir_windows: C:\screenshot-annotator
upload_dir: "{{ app_dir }}/uploads"
```

## Implementation Order

1. **Create Ansible structure** - directories, ansible.cfg, inventory
2. **Common role** - Docker installation for both OS types
3. **HAProxy role** - Load balancer configuration
4. **Keepalived role** - VIP failover (with Windows workaround)
5. **PostgreSQL role** - Primary/replica replication
6. **Redis role** - Container setup
7. **Application role** - Deploy containers
8. **Lsyncd role** - File synchronization
9. **GitHub Actions** - CI/CD workflow
10. **Documentation** - Setup guide and failover procedures

## Windows 10/11 Considerations

Since Windows 10/11 uses Docker Desktop with WSL2:

- **Keepalived**: Run in a Docker container with host networking (limited)
- **Lsyncd**: Not available - Windows is rsync RECEIVER only
- **Paths**: Use Windows paths in templates (`C:\screenshot-annotator`)
- **Ansible**: Connect via SSH (OpenSSH Server) or WinRM

Alternative for Keepalived on Windows 10/11:
- Skip VIP on Windows, use DNS-based failover instead
- Or use nginx on Windows without Keepalived (manual failover)

## GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `ANSIBLE_SSH_KEY` | Private key for Ansible to connect to servers |
| `ANSIBLE_VAULT_PASSWORD` | Password for ansible-vault (secrets) |
| `REDHAT_HOST` | Primary server IP/hostname |
| `WINDOWS_HOST` | Secondary server IP/hostname |

## Usage After Implementation

```bash
# From dev machine (in ansible/ directory)

# Initial setup (run once)
ansible-playbook playbooks/provision.yml

# Deploy application
ansible-playbook playbooks/deploy.yml

# Deploy to specific server only
ansible-playbook playbooks/deploy.yml --limit primary

# Rollback
ansible-playbook playbooks/rollback.yml

# Check status
ansible all -m shell -a "docker ps"
```

## Notes

- **Keepalived on Windows 10/11 is limited** - VIP failover may require DNS-based approach instead
- **PostgreSQL failover is manual** - To prevent split-brain scenarios
- **Lsyncd is one-way** - Primary → Secondary only
- **Both servers run identical Linux containers** - Windows uses Docker Desktop's WSL2 backend
