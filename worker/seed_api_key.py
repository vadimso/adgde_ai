# seed_api_key.py
from database import SessionLocal, ApiKey
import hashlib, uuid
from datetime import datetime
import os

# Read API_KEY from env or fallback
API_KEY = os.getenv("API_KEY", "123456")
CUSTOMER_ID = os.getenv("CUSTOMER_ID", "customer_123")

key_hash = hashlib.sha256(API_KEY.encode()).hexdigest()

db = SessionLocal()

# Check if key already exists
existing = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
if not existing:
    new_key = ApiKey(
        id=str(uuid.uuid4()),
        customer_id=CUSTOMER_ID,
        key_hash=key_hash,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(new_key)
    db.commit()
    print(f"API key seeded for customer_id={CUSTOMER_ID}")
else:
    print("API key already exists, skipping seeding.")

db.close()