"""
Locust load testing script for Export/Import API

Usage:
    pip install locust
    locust -f loadtest.py --host=http://localhost:8080 --users=100 --spawn-rate=10
"""

from locust import HttpUser, task, between
import uuid
import json
import time


class APIKey:
    """Helper to get API key from environment or generate test key"""
    test_key = "test_key_550e8400e29b41d4a716446655440000"


class ExportUser(HttpUser):
    """Simulates users creating exports and checking status"""
    wait_time = between(2, 5)

    @task(3)
    def create_export(self):
        """Create export job"""
        headers = {
            "Authorization": f"Bearer {APIKey.test_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "format": "json",
            "filters": {"date_from": "2024-01-01"}
        }

        response = self.client.post(
            "/api/v1/exports",
            json=payload,
            headers=headers,
            name="/api/v1/exports"
        )

        if response.status_code == 202:
            job_id = response.json().get("job_id")
            self.job_id = job_id
            print(f"Created export: {job_id}")

    @task(1)
    def check_export_status(self):
        """Check status of export"""
        if hasattr(self, 'job_id'):
            headers = {"Authorization": f"Bearer {APIKey.test_key}"}

            response = self.client.get(
                f"/api/v1/exports/{self.job_id}",
                headers=headers,
                name="/api/v1/exports/{job_id}"
            )

            if response.status_code == 200:
                status = response.json().get("status")
                print(f"Status: {status}")

    @task(1)
    def download_export(self):
        """Try to download export (will fail if not complete)"""
        if hasattr(self, 'job_id'):
            headers = {"Authorization": f"Bearer {APIKey.test_key}"}

            response = self.client.get(
                f"/api/v1/exports/{self.job_id}/download",
                headers=headers,
                name="/api/v1/exports/{job_id}/download"
            )

            # 400 = not complete yet (expected), 200 = success
            if response.status_code in [200, 400]:
                print(f"Download attempt: {response.status_code}")

    @task(1)
    def health_check(self):
        """Periodic health check"""
        response = self.client.get(
            "/health",
            name="/health"
        )


class ImportUser(HttpUser):
    """Simulates users importing files"""
    wait_time = between(5, 10)
    jobs = []

    @task(2)
    def upload_import(self):
        """Upload file for import"""
        headers = {"Authorization": f"Bearer {APIKey.test_key}"}

        # Create test CSV file content
        csv_content = "id,name,value\n"
        for i in range(1000):
            csv_content += f"{i},record_{i},{i * 10}\n"

        files = {
            'file': ('test_data.csv', csv_content.encode(), 'text/csv')
        }
        data = {'format': 'csv'}

        response = self.client.post(
            "/api/v1/imports",
            files=files,
            data=data,
            headers=headers,
            name="/api/v1/imports"
        )

        if response.status_code == 202:
            job_id = response.json().get("job_id")
            self.jobs.append(job_id)
            print(f"Created import: {job_id}")

    @task(1)
    def check_import_status(self):
        """Check import status"""
        if self.jobs:
            job_id = self.jobs[0]
            headers = {"Authorization": f"Bearer {APIKey.test_key}"}

            response = self.client.get(
                f"/api/v1/imports/{job_id}",
                headers=headers,
                name="/api/v1/imports/{job_id}"
            )

            if response.status_code == 200:
                status = response.json().get("status")
                records = response.json().get("records_imported", 0)
                print(f"Import status: {status}, records: {records}")


class MixedUser(HttpUser):
    """Mixed workload - both exports and imports"""
    wait_time = between(3, 7)

    def on_start(self):
        """Called when user starts"""
        self.export_jobs = []
        self.import_jobs = []

    @task(2)
    def export_workflow(self):
        """Full export workflow"""
        headers = {
            "Authorization": f"Bearer {APIKey.test_key}",
            "Content-Type": "application/json"
        }

        # Create export
        create_response = self.client.post(
            "/api/v1/exports",
            json={"format": "json"},
            headers=headers,
            name="/api/v1/exports"
        )

        if create_response.status_code == 202:
            job_id = create_response.json()["job_id"]
            self.export_jobs.append(job_id)

            # Check status
            time.sleep(1)
            for i in range(15):  # Check up to 15 times
                status_response = self.client.get(
                    f"/api/v1/exports/{job_id}",
                    headers=headers,
                    name="/api/v1/exports/{job_id}"
                )
                status = status_response.json()["status"]

                if status == "completed":
                    # Try to download
                    self.client.get(
                        f"/api/v1/exports/{job_id}/download",
                        headers=headers,
                        name="/api/v1/exports/{job_id}/download"
                    )
                    break

                time.sleep(1)

    @task(1)
    def import_workflow(self):
        """Full import workflow"""
        headers = {"Authorization": f"Bearer {APIKey.test_key}"}

        # Create test JSON
        json_content = json.dumps({
            "records": [{"id": i, "value": i * 2} for i in range(100)]
        })

        files = {'file': ('data.json', json_content.encode(), 'application/json')}
        data = {'format': 'json'}

        # Upload
        upload_response = self.client.post(
            "/api/v1/imports",
            files=files,
            data=data,
            headers=headers,
            name="/api/v1/imports"
        )

        if upload_response.status_code == 202:
            job_id = upload_response.json()["job_id"]
            self.import_jobs.append(job_id)

            # Wait for completion
            for i in range(15):
                status_response = self.client.get(
                    f"/api/v1/imports/{job_id}",
                    headers=headers,
                    name="/api/v1/imports/{job_id}"
                )
                status = status_response.json()["status"]

                if status in ["completed", "failed"]:
                    break

                time.sleep(1)

    @task(1)
    def health_check(self):
        """Monitor system health"""
        self.client.get("/health", name="/health")


# Test configurations for different scenarios

class LightLoadTest(HttpUser):
    """10 users, moderate requests"""
    wait_time = between(5, 10)

    @task
    def user_behavior(self):
        headers = {
            "Authorization": f"Bearer {APIKey.test_key}",
            "Content-Type": "application/json"
        }
        self.client.post(
            "/api/v1/exports",
            json={"format": "json"},
            headers=headers
        )


class HeavyLoadTest(HttpUser):
    """100+ users, aggressive requests - test system limits"""
    wait_time = between(1, 3)

    @task(5)
    def export_stress(self):
        """Rapid export creation"""
        headers = {
            "Authorization": f"Bearer {APIKey.test_key}",
            "Content-Type": "application/json"
        }
        self.client.post(
            "/api/v1/exports",
            json={"format": json.choice(['json', 'csv', 'xml'])},
            headers=headers,
            name="/api/v1/exports"
        )

    @task(3)
    def status_check_storm(self):
        """Many status checks"""
        headers = {"Authorization": f"Bearer {APIKey.test_key}"}
        # Check random job (will 404 but that's expected)
        self.client.get(
            f"/api/v1/exports/{str(uuid.uuid4())}",
            headers=headers,
            name="/api/v1/exports/{random}"
        )

    @task(2)
    def rate_limit_test(self):
        """Test rate limiting"""
        for _ in range(5):
            self.client.get("/health")  # Rapid requests


if __name__ == "__main__":
    print("""
    Load Testing Scenarios:

    1. Realistic Load (Mixed):
       locust -f loadtest.py --host=http://localhost:8080 -u MixedUser --users 50

    2. Export Heavy:
       locust -f loadtest.py --host=http://localhost:8080 -u ExportUser --users 100

    3. Import Heavy:
       locust -f loadtest.py --host=http://localhost:8080 -u ImportUser --users 50

    4. Stress Test:
       locust -f loadtest.py --host=http://localhost:8080 -u HeavyLoadTest --users 500

    5. Light Load (Baseline):
       locust -f loadtest.py --host=http://localhost:8080 -u LightLoadTest --users 20
    """)
