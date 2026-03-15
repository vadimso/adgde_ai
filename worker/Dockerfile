FROM python:3.11

WORKDIR /app
COPY seed_api_key.py /app/seed_api_key.py
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "sh", "-c", "python /app/seed_api_key.py && uvicorn main:app --host 0.0.0.0 --port 8000"]