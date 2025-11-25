FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Node.js (for GitHub MCP server) and other OS deps
RUN apt-get update && \
    apt-get install -y curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json /app/
RUN npm install --omit=dev

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

CMD ["uvicorn", "app:api", "--host", "0.0.0.0", "--port", "8080"]

