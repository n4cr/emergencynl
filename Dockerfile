# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy the application code
COPY . .

# Make the entrypoint script executable
RUN chmod +x /app/scripts/entrypoint.sh

# Default command (web server)
CMD ["gunicorn", "-b", "0.0.0.0:8000", "--config", "gunicorn.conf.py", "wsgi:app"] 