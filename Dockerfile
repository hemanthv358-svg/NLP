FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . /app
USER appuser
EXPOSE 8000
CMD ["python", "bot.py"]
