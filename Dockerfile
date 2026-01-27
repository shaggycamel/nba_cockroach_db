# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
# 1. default-jre is required for tabula-py (Java)
# 2. build-essential and gcc for sqlalchemy/pandas if needed
# 3. libgomp1 is often needed for high-performance Polars operations
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    default-jre \
    build-essential \
    gcc \
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Install Python dependencies
# We use a single RUN command to keep the image layer count low
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Command to run your script (assuming your main script is main.py)
# ENTRYPOINT allows you to pass arguments like 'argv' easily
ENTRYPOINT ["python", "."]

