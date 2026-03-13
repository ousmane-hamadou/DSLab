FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8090

ENV PYTHONPATH=/app
# Lancement de l'application
CMD ["uvicorn", "app.interfaces.web:app", "--host", "0.0.0.0", "--port", "8090"]