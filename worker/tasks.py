from celery import Celery
import time
from minio import Minio
from io import BytesIO
import os
import logging
import json
from datetime import datetime
import sys

# Add parent directory to path to import database
sys.path.insert(0, '/api')

from app.database import SessionLocal, ExportJob, ImportJob

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery configuration
celery = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_BACKEND_URL", "redis://redis:6379/1")
)

# MinIO configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")


def get_minio_client():
    """Create MinIO client"""
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )


def update_job_status(job_id, status, progress=None, error_message=None, file_size=None, file_path=None):
    """Update export job status in database"""
    try:
        db = SessionLocal()
        job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
        if job:
            job.status = status
            if progress is not None:
                job.progress = progress
            if status == "processing" and not job.started_at:
                job.started_at = datetime.utcnow()
            if status == "completed":
                job.completed_at = datetime.utcnow()
            if status == "failed":
                job.completed_at = datetime.utcnow()
            if error_message:
                job.error_message = error_message
            if file_size:
                job.file_size = file_size
            if file_path:
                job.file_path = file_path
            db.commit()
            logger.info(f"Export {job_id} status updated to {status}")
        db.close()
    except Exception as e:
        logger.error(f"Failed to update export job status: {e}")


@celery.task(
    bind=True,
    time_limit=600,  # Hard limit: 10 minutes
    soft_time_limit=580,  # Soft limit: 9min 40sec for graceful shutdown
    max_retries=3,
    default_retry_delay=60
)
def export_task(self, job_id, customer_id, export_format="json"):
    """
    Async export task with error handling and timeout

    Args:
        job_id: Unique export job ID
        customer_id: Customer requesting the export
        export_format: Format to export (json, csv, xml)
    """
    try:
        logger.info(f"Starting export task {job_id} for customer {customer_id}")

        # Update status to processing
        update_job_status(job_id, "processing", progress=0)

        # Simulate data generation (in real scenario, fetch from DB)
        logger.info(f"Generating export data for {job_id}")

        # Simulate long-running operation with progress
        simulated_size = 1024 * 100  # 100KB simulated data
        data_chunks = []

        for i in range(10):
            time.sleep(1)  # Simulate work (10 seconds total)
            progress = (i + 1) * 10
            update_job_status(job_id, "processing", progress=progress)
            logger.info(f"Export {job_id} progress: {progress}%")

            # Generate chunk data
            chunk = {"batch": i, "records": list(range(100))}
            data_chunks.append(chunk)

        # Combine data
        if export_format == "json":
            export_data = json.dumps({"data": data_chunks, "count": len(data_chunks)}).encode()
        elif export_format == "csv":
            export_data = b"batch,record\n" + b"\n".join(
                f"{i},{j}".encode() for i in range(len(data_chunks)) for j in range(100)
            )
        else:  # xml
            export_data = b"<root><items>" + b"".join(
                f"<item><batch>{i}</batch></item>".encode() for i in range(len(data_chunks))
            ) + b"</root>"

        # Upload to MinIO
        logger.info(f"Uploading export {job_id} to MinIO ({len(export_data)} bytes)")
        client = get_minio_client()

        file_name = f"exports/{job_id}.{export_format}"
        client.put_object(
            "exports",
            f"{job_id}.{export_format}",
            BytesIO(export_data),
            length=len(export_data)
        )

        # Update job as completed
        update_job_status(
            job_id,
            "completed",
            progress=100,
            file_size=len(export_data),
            file_path=f"{job_id}.{export_format}"
        )

        logger.info(f"Export {job_id} completed successfully")
        return {"status": "completed", "job_id": job_id, "size": len(export_data)}

    except Exception as exc:
        logger.error(f"Export task {job_id} failed: {str(exc)}", exc_info=True)

        # Update job as failed
        update_job_status(
            job_id,
            "failed",
            error_message=f"Export failed: {str(exc)}"
        )

        # Retry with exponential backoff
        try:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        except Exception as retry_exc:
            logger.error(f"Export {job_id} max retries exceeded: {str(retry_exc)}")
            raise


def update_import_job_status(job_id, status, progress=None, error_message=None, records_imported=None):
    """Update import job status in database"""
    try:
        db = SessionLocal()
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job:
            job.status = status
            if progress is not None:
                job.progress = progress
            if status == "processing" and not job.started_at:
                job.started_at = datetime.utcnow()
            if status in ["completed", "failed"]:
                job.completed_at = datetime.utcnow()
            if error_message:
                job.error_message = error_message
            if records_imported is not None:
                job.records_imported = records_imported
            db.commit()
            logger.info(f"Import {job_id} status updated to {status}")
        db.close()
    except Exception as e:
        logger.error(f"Failed to update import job status: {e}")


@celery.task(
    bind=True,
    time_limit=600,  # 10 minutes max
    soft_time_limit=580,
    max_retries=3,
    default_retry_delay=60
)
def import_task(self, job_id, customer_id, import_format="json"):
    """
    Async import task

    Args:
        job_id: Unique import job ID
        customer_id: Customer requesting the import
        import_format: Format of file (json, csv, xml)
    """
    try:
        logger.info(f"Starting import task {job_id} for customer {customer_id}")

        update_import_job_status(job_id, "processing", progress=0)

        # Download file from MinIO
        client = get_minio_client()
        file_path = f"{job_id}.{import_format}"

        logger.info(f"Downloading import file {file_path} from MinIO")
        response = client.get_object("imports", file_path)
        file_content = response.read()
        response.close()

        # Parse based on format
        logger.info(f"Parsing {import_format} file for import {job_id}")

        if import_format == "json":
            data = json.loads(file_content.decode())
            records = data.get("data", [])
        elif import_format == "csv":
            lines = file_content.decode().split("\n")[1:]  # Skip header
            records = [line.split(",") for line in lines if line]
        else:  # xml
            records = []  # Simplified - would use XML parser in reality

        record_count = len(records)

        # Simulate processing with progress
        for i, record in enumerate(records):
            if i % max(1, record_count // 10) == 0:
                progress = int((i / record_count) * 100)
                update_import_job_status(job_id, "processing", progress=progress)
                time.sleep(0.1)  # Simulate DB write

        # Update as completed
        update_import_job_status(
            job_id,
            "completed",
            progress=100,
            records_imported=record_count
        )

        logger.info(f"Import {job_id} completed with {record_count} records")
        return {"status": "completed", "job_id": job_id, "records": record_count}

    except Exception as exc:
        logger.error(f"Import task {job_id} failed: {str(exc)}", exc_info=True)

        update_import_job_status(
            job_id,
            "failed",
            error_message=f"Import failed: {str(exc)}"
        )

        try:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        except Exception as retry_exc:
            logger.error(f"Import {job_id} max retries exceeded: {str(retry_exc)}")
            raise
