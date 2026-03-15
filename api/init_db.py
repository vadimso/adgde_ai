"""
Database initialization script
Creates tables and seed data
"""
import os
import sys
from datetime import datetime, timedelta
import uuid

# Add parent directory to path
sys.path.insert(0, '/api')

from database import init_db, SessionLocal, Customer, ApiKey
from auth import hash_key

def create_seed_data():
    """Create initial test data"""
    db = SessionLocal()

    try:
        # Create a test customer
        customer_id = str(uuid.uuid4())
        customer = Customer(
            id=customer_id,
            name="Test Customer",
            tier="pro",
            max_file_size=100 * 1024 * 1024,  # 100MB
            rate_limit_per_hour=1000,
            is_active=True
        )
        db.add(customer)
        db.commit()

        # Create an API key for the test customer
        api_key_value = f"test_key_{str(uuid.uuid4())}"
        api_key = ApiKey(
            id=str(uuid.uuid4()),
            customer_id=customer_id,
            key_hash=hash_key(api_key_value),
            description="Test API Key",
            expires_at=datetime.utcnow() + timedelta(days=365),
            is_active=True,
            rate_limit_per_hour=1000
        )
        db.add(api_key)
        db.commit()

        print(f"✓ Created test customer: {customer.name}")
        print(f"✓ API Key: {api_key_value}")
        print(f"✓ Use this key in Authorization header: Bearer {api_key_value}")

    except Exception as e:
        print(f"✗ Error creating seed data: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("Initializing database...")

    # Create tables
    init_db()
    print("✓ Database tables created")

    # Create seed data
    create_seed_data()

    print("✓ Database initialization complete")
