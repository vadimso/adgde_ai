from fastapi import HTTPException, Depends, status, Header
from sqlalchemy.orm import Session
import os
import hashlib
from datetime import datetime
from typing import Optional
from database import ApiKey, get_db


def hash_key(key: str) -> str:
    """Hash API key for storage"""
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> str:
    """
    Verify API key and return customer_id
    Expected header: Authorization: Bearer <api_key>
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Parse "Bearer <token>"
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    if not token or len(token) < 10:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key_hash = hash_key(token)

    api_key = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active == True
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check expiration
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last used time
    api_key.last_used_at = datetime.utcnow()
    db.commit()

    return api_key.customer_id


