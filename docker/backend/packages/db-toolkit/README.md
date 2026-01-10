# db-toolkit

Database utilities for FastAPI with SQLAlchemy async.

## Features

- Async engine factory with sensible pool defaults
- Session dependency factory for FastAPI
- Health check integration with deploy-toolkit
- Base model classes with common mixins

## Installation

```bash
pip install db-toolkit[postgres]  # For PostgreSQL
pip install db-toolkit[sqlite]    # For SQLite
```

## Usage

```python
from db_toolkit import (
    create_engine,
    create_session_maker,
    create_get_db,
    DatabaseHealthCheck,
    Base,
    TimestampMixin,
)
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Setup
engine = create_engine(settings.DATABASE_URL)
session_maker = create_session_maker(engine)
get_db = create_get_db(session_maker)

# Use in routes
@app.get("/items")
async def get_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item))
    return result.scalars().all()

# Health check with deploy-toolkit
app = create_app(
    health_checks=[DatabaseHealthCheck(engine)],
)
```

## Base Models

```python
from db_toolkit import Base, TimestampMixin, SoftDeleteMixin

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    # created_at and updated_at are added automatically
```
