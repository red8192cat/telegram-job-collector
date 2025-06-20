FROM python:3.11-alpine
WORKDIR /app
# Install cron and other dependencies
RUN apk add --no-cache dcron
# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy application code
COPY src/ ./src/
COPY config.json .
COPY health_check.py .     # ← This line should be added
# Create data directory for persistent storage
RUN mkdir -p /app/data
# Set permissions for cron
RUN chmod +x src/bot.py
EXPOSE 8080
CMD ["python", "src/bot.py"]
