# Pull official base image
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /usr/src/app

# Set environment variables
ENV PIP_ROOT_USER_ACTION=ignore \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies in a single layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    netcat-openbsd \
    gcc \
    libpq-dev \
    libglib2.0-0 \
    libglib2.0-dev \
    libopus0 \
    libvpx7 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create secrets directory
RUN mkdir -p /etc/secrets && chmod 700 /etc/secrets

# Install Python dependencies
COPY ./requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .