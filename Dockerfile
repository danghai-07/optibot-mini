FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY src ./src
COPY data ./data
COPY state ./state

# Persist /app/state via a Railway Volume for daily delta sync
CMD ["python", "main.py"]
