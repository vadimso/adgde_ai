from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class ExportRequest(BaseModel):
    """Request model for export endpoint"""
    format: str = Field(default="json", description="Export format: json, csv, xml")
    filters: Optional[dict] = Field(default=None, description="Optional filter criteria")

    @field_validator('format')
    @classmethod
    def validate_format(cls, v):
        allowed = ['json', 'csv', 'xml']
        if v not in allowed:
            raise ValueError(f'format must be one of: {", ".join(allowed)}')
        return v


class ExportResponse(BaseModel):
    """Response model for export creation"""
    job_id: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ExportStatus(BaseModel):
    """Export job status response"""
    job_id: str
    status: str
    progress: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    file_size: Optional[int]

    class Config:
        from_attributes = True


class ImportRequest(BaseModel):
    """Metadata for import requests"""
    format: str = Field(default="json")
    skip_validation: bool = Field(default=False)

    @field_validator('format')
    @classmethod
    def validate_format(cls, v):
        allowed = ['json', 'csv', 'xml']
        if v not in allowed:
            raise ValueError(f'format must be one of: {", ".join(allowed)}')
        return v


class ImportResponse(BaseModel):
    """Response model for import creation"""
    job_id: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ImportStatus(BaseModel):
    """Import job status response"""
    job_id: str
    status: str
    progress: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    records_imported: Optional[int]

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str = "1.0.0"
