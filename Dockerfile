# One image for the web app and the scraper job: same code, different command (see docker-compose.yml)
FROM python:3.12-slim
WORKDIR /app
COPY src/enrichment/requirements.txt /tmp/enrichment.txt
COPY src/server/requirements.txt /tmp/server.txt
RUN pip install --no-cache-dir -r /tmp/enrichment.txt -r /tmp/server.txt
COPY src ./src
ENV PYTHONUNBUFFERED=1 PYTHON=python
CMD ["python", "src/server/app.py"]
