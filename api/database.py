from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, String, DateTime, Enum, Integer, Text, Boolean
from datetime import datetime
import enum
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://export:password123@postgres:5432/exports"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(String(36), primary_key=True)
    customer_id = Column(String(36), nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False)
    progress = Column(Integer, default=0)  # 0-100
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_path = Column(String(255), nullable=True)  # MinIO path


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(String(36), primary_key=True)
    customer_id = Column(String(36), nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_path = Column(String(255), nullable=True)
    records_imported = Column(Integer, default=0)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True)
    customer_id = Column(String(36), nullable=False, index=True)
    key_hash = Column(String(255), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    rate_limit_per_hour = Column(Integer, default=100)
    last_used_at = Column(DateTime, nullable=True)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    tier = Column(String(20), default="free")  # free, pro, enterprise
    max_file_size = Column(Integer, default=100 * 1024 * 1024)  # 100MB default
    rate_limit_per_hour = Column(Integer, default=100)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)
