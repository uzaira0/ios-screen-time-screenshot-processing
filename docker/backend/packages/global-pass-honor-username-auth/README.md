# global-pass-honor-username-auth

Shared authentication package for internal research tools using a simple site password + honor-system username model.

## Features

- **Site Password**: Single shared password for all users (optional)
- **Honor-System Username**: Users self-identify via header for audit logging
- **Timing Attack Protection**: Uses `secrets.compare_digest()` for password verification
- **Two Variants**:
  - **Variant A**: No user database, username stored as string
  - **Variant B**: Users auto-created in database with IDs and roles

## Installation

```bash
# With FastAPI support (recommended)
pip install global-pass-honor-username-auth[fastapi]

# With SQLAlchemy support (for Variant B)
pip install global-pass-honor-username-auth[sqlalchemy]

# All extras
pip install global-pass-honor-username-auth[all]
```

## Quick Start (Variant A)

```python
from global_auth import AuthSettingsMixin, create_auth_router, create_verify_site_password
from pydantic_settings import BaseSettings

class Settings(AuthSettingsMixin, BaseSettings):
    DATABASE_URL: str = "sqlite:///app.db"

def get_settings() -> Settings:
    return Settings()

# Create auth router
auth_router = create_auth_router(get_settings, variant="a")
app.include_router(auth_router, prefix="/api/v1/auth")

# Protect endpoints
verify_site_password = create_verify_site_password(get_settings)

@router.get("/protected")
async def protected(
    _: Annotated[str, Depends(verify_site_password)],
    username: str = Depends(get_username_required),
):
    return {"message": f"Hello, {username}"}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SITE_PASSWORD` | (empty) | Shared password. Empty = no auth required |
| `ADMIN_USERNAMES` | `admin` | Comma-separated admin usernames |

## HTTP Headers

| Header | Description |
|--------|-------------|
| `X-Site-Password` | Site password (if required) |
| `X-Username` | Honor-system username |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/status` | GET | Check if password required |
| `/auth/verify` | POST | Verify password |
| `/auth/login` | POST | Login (Variant B only) |
| `/auth/me` | GET | Current user (Variant B only) |
