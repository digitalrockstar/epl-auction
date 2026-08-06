import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# On Render/Neon you'll set DATABASE_URL as an env var.
# Locally, falls back to a sqlite file so you can develop without a real DB.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_dev.db")

# Neon/Render give postgres:// urls, sqlalchemy wants postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine_kwargs = {"connect_args": connect_args}
if not DATABASE_URL.startswith("sqlite"):
    # Neon (and most managed Postgres) silently drops idle SSL connections.
    # pre_ping tests the connection before handing it out and transparently
    # reconnects if it's dead; recycle forces a fresh connection periodically
    # so we never hand out one that's about to be dropped mid-request.
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 280

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
