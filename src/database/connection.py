"""Database connection and session management"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager
from src.shared.utils.logger_config import setup_logger

logger = setup_logger(__name__)

# Database configuration
DATABASE_DIR = "/app/data"
DATABASE_PATH = os.path.join(DATABASE_DIR, "ael_erp.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Ensure data directory exists
os.makedirs(DATABASE_DIR, exist_ok=True)

# Create engine with SQLite optimizations
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,  # Allow multiple threads (Streamlit)
        "timeout": 30  # 30 second timeout for locks
    },
    echo=False,  # Set to True for SQL query logging during development
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20
)

# Enable WAL mode for better concurrency
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set SQLite pragmas for optimal performance"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
    cursor.execute("PRAGMA busy_timeout=5000")  # 5 second timeout
    cursor.execute("PRAGMA synchronous=NORMAL")  # Balance between safety and speed
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
    cursor.execute("PRAGMA foreign_keys=ON")  # Enable foreign key constraints
    cursor.close()
    logger.info("SQLite pragmas configured: WAL mode enabled, foreign keys ON")

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI/Streamlit
def get_db():
    """Get database session (dependency injection pattern)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_session():
    """Context manager for database sessions"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

logger.info(f"Database initialized at: {DATABASE_PATH}")
