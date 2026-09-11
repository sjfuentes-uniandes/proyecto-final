FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 SERVICE_NAME=cotizacion
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY common ./common
COPY common/healthcheck /app/healthcheck
COPY cotizacion/app ./app
RUN chmod 755 /app/healthcheck
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=2s --start-period=30s --retries=2 CMD ["/app/healthcheck"]
CMD ["python", "-m", "common.serve"]
