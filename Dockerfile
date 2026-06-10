FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and directories
COPY app.py /app/
COPY glinet_blacklist.py /app/
COPY templates /app/templates
COPY static /app/static

# Create uploads folder for chore verification proof pictures
RUN mkdir -p /app/static/uploads

# Add entrypoint that can promote Docker secrets (e.g. router password) into env vars
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/docker-entrypoint.sh"]
# Use --workers 1 so the background scheduler (daily 4am reset) only runs in one process.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "app:app"]
