# Playwright base image with all system dependencies
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install only Chromium browser (hemat RAM)
RUN playwright install chromium

# Copy application code
COPY . .

# Start bot
CMD ["python3", "bot.py"]
