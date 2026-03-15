from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from celery import Celery
import uuid
import os
import logging
from datetime import datetime
from typing import Optional

from database import get_db, init_db, ExportJob, ImportJob, Customer
from auth import verify_api_key
from schemas import (
    ExportRequest, ExportResponse, ExportStatus,
    ImportResponse, ImportStatus, HealthResponse
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
init_db()

# FastAPI app
app = FastAPI(
    title="Export/Import API",
    version="1.0.0",
    description="API for async export and import operations"
)

# CORS configuration - only allow specific origins
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition", "X-Job-Id"],
    max_age=3600,
)

# Celery configuration
celery = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_BACKEND_URL", "redis://redis:6379/1")
)


# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint - no authentication required"""
    return {"status": "healthy", "version": "1.0.0"}


# ==================== EXPORT ENDPOINTS ====================

@app.post(
    "/api/v1/exports",
    response_model=ExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create export job",
    tags=["Exports"]
)
async def create_export(
    request: ExportRequest,
    customer_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """
    Create a new export job.

    Returns 202 Accepted with job_id for tracking.

    **Headers:** Authorization: Bearer {api_key}

    **Request Body:**
    - format: json, csv, or xml
    - filters: optional filter criteria

    **Returns:** job_id to check status later
    """
    # Log request
    logger.info(
        f"Export requested",
        extra={
            "customer_id": customer_id,
            "format": request.format,
            "user_agent": user_agent
        }
    )

    # Generate unique job ID
    job_id = str(uuid.uuid4())

    # Create job record in database
    job = ExportJob(
        id=job_id,
        customer_id=customer_id,
        status="pending",
        created_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()

    # Queue async task to worker
    celery.send_task(
        'tasks.export_task',
        args=(job_id, customer_id, request.format),
        task_id=job_id,
        expires=3600  # Task expires in 1 hour
    )

    logger.info(f"Export job queued: {job_id}")

    return ExportResponse(
        job_id=job_id,
        status="pending",
        created_at=job.created_at
    )


@app.get(
    "/api/v1/exports/{job_id}",
    response_model=ExportStatus,
    summary="Get export status",
    tags=["Exports"]
)
async def get_export_status(
    job_id: str,
    customer_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Get the status of an export job.

    **Parameters:**
    - job_id: The job ID returned from create_export

    **Returns:** Current status, progress, and any error messages
    """
    job = db.query(ExportJob).filter(
        ExportJob.id == job_id,
        ExportJob.customer_id == customer_id  # Verify ownership
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export job {job_id} not found"
        )

    return ExportStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        file_size=job.file_size
    )


@app.get(
    "/api/v1/exports/{job_id}/download",
    summary="Download export file",
    tags=["Exports"]
)
async def download_export(
    job_id: str,
    customer_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Download completed export file.

    **Returns:** File stream (returns 303 redirect to presigned MinIO URL)
    """
    job = db.query(ExportJob).filter(
        ExportJob.id == job_id,
        ExportJob.customer_id == customer_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export job {job_id} not found"
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export job is {job.status}, not completed yet"
        )

    # Generate presigned URL from MinIO
    from minio import Minio
    minio_client = Minio(
        os.getenv("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "password"),
        secure=False
    )

    try:
        url = minio_client.get_presigned_download_url(
            "exports",
            job.file_path,
            expires=3600  # URL valid for 1 hour
        )
        logger.info(f"Download requested for export {job_id}")
        return {"download_url": url, "expires_in_seconds": 3600}
    except Exception as e:
        logger.error(f"Failed to generate download URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download link"
        )


# ==================== IMPORT ENDPOINTS ====================

@app.post(
    "/api/v1/imports",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create import job",
    tags=["Imports"]
)
async def create_import(
    file: UploadFile = File(...),
    format: str = "json",
    customer_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Upload file for import processing.

    **Parameters:**
    - file: multipart file upload (max 100MB)
    - format: json, csv, or xml

    **Returns:** job_id for tracking progress
    """
    max_size = 100 * 1024 * 1024  # 100MB

    # Validate file size
    if file.size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size is {max_size} bytes"
        )

    # Validate file format
    if format not in ['json', 'csv', 'xml']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format must be json, csv, or xml"
        )

    logger.info(
        f"Import requested",
        extra={
            "customer_id": customer_id,
            "filename": file.filename,
            "file_size": file.size,
            "format": format
        }
    )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Create job record
    job = ImportJob(
        id=job_id,
        customer_id=customer_id,
        status="pending",
        file_size=file.size,
        created_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()

    # Upload file to MinIO temp location
    from minio import Minio
    minio_client = Minio(
        os.getenv("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "password"),
        secure=False
    )

    try:
        content = await file.read()
        import io
        minio_client.put_object(
            "imports",
            f"{job_id}.{format}",
            io.BytesIO(content),
            length=len(content)
        )

        # Update job with file path
        job.file_path = f"{job_id}.{format}"
        db.commit()

        # Queue import task
        celery.send_task(
            'tasks.import_task',
            args=(job_id, customer_id, format),
            task_id=job_id,
            expires=3600
        )

        logger.info(f"Import job queued: {job_id}")

        return ImportResponse(
            job_id=job_id,
            status="pending",
            created_at=job.created_at
        )

    except Exception as e:
        logger.error(f"Failed to upload import file: {str(e)}")
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process import file"
        )


@app.get(
    "/api/v1/imports/{job_id}",
    response_model=ImportStatus,
    summary="Get import status",
    tags=["Imports"]
)
async def get_import_status(
    job_id: str,
    customer_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Get the status of an import job.
    """
    job = db.query(ImportJob).filter(
        ImportJob.id == job_id,
        ImportJob.customer_id == customer_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import job {job_id} not found"
        )

    return ImportStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        records_imported=job.records_imported
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
