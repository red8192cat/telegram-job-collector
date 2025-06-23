#!/bin/bash
set -e

echo "📦 Moving health_check.py to src/ and updating Docker references..."

# Move health_check.py to src/
echo "📁 Moving health_check.py to src/"
mv health_check.py src/

# Update Dockerfile
echo "📝 Updating Dockerfile..."
cat > Dockerfile << 'EOF'
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
    openssl-dev

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
EOF

echo "✅ Updated Dockerfile"

# Update docker-compose.yml
echo "📝 Updating docker-compose.yml..."
cat > docker-compose.yml << 'EOF'
services:
  telegram-bot:
    build: .
    container_name: job-collector-bot
    env_file:
      - data/config/bot-secrets.env
    environment:
      - DATABASE_PATH=/app/data/bot.db
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    networks:
      - bot-network
    healthcheck:
      test: ["CMD", "python", "/app/src/health_check.py"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  bot-network:
    driver: bridge
EOF

echo "✅ Updated docker-compose.yml"

# Verify files are in correct locations
echo "🔍 Verifying file structure..."
if [ -f "src/health_check.py" ]; then
    echo "✅ health_check.py is now in src/"
else
    echo "❌ health_check.py not found in src/"
    exit 1
fi

if [ -f "src/bot.py" ]; then
    echo "✅ bot.py confirmed in src/"
else
    echo "❌ bot.py not found in src/"
    exit 1
fi

# Show clean project structure
echo ""
echo "✅ Clean project structure achieved!"
echo ""
echo "📁 Updated structure:"
echo "telegram-job-collector/"
echo "├── docker-compose.yml        # ← Updated health check path"
echo "├── Dockerfile               # ← Updated COPY commands"
echo "├── requirements.txt"
echo "├── README.md"
echo "├── src/                     # ← All Python code here"
echo "│   ├── bot.py"
echo "│   ├── health_check.py      # ← Moved here"
echo "│   ├── handlers/"
echo "│   ├── matching/"
echo "│   ├── monitoring/"
echo "│   ├── storage/"
echo "│   └── utils/"
echo "└── data/                    # ← All runtime data here"
echo "    ├── config/"
echo "    │   ├── bot-secrets.env"
echo "    │   ├── channels.json"
echo "    │   └── users.json"
echo "    └── bot.db"
echo ""
echo "🚀 Ready to rebuild:"
echo "   docker-compose build --no-cache"
echo "   docker-compose up -d"
echo ""
echo "🔍 Test health check:"
echo "   docker-compose exec telegram-bot python /app/src/health_check.py"