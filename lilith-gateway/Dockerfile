FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for libvirt
RUN apt-get update && apt-get install -y --no-install-recommends \
    libvirt-dev \
    pkg-config \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run the server
CMD ["python", "gateway_server.py"]