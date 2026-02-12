FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY skills/ ./skills/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Runtime user (don't run as root)
RUN useradd --create-home agent
RUN chown -R agent:agent /app
USER agent

ENTRYPOINT ["./entrypoint.sh"]
