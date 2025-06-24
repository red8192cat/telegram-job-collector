FROM python:3.11-alpine
WORKDIR /app

# Install required packages including Rust for cryptg
RUN apk add --no-cache \
    dcron \
    sqlite \
    gcc \
    musl-dev \
    libffi-dev \
    cargo \
    rust \
    openssl-dev \
    htop \
    ncdu \
    curl \
    nano

# Upgrade pip to ensure we can use prebuilt wheels
RUN pip install --upgrade pip

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create data directory for persistent storage (sessions will be here too)
RUN mkdir -p /app/data

# Set permissions
RUN chmod +x src/bot.py
RUN chmod +x src/health_check.py

EXPOSE 8080
CMD ["python", "src/bot.py"]
