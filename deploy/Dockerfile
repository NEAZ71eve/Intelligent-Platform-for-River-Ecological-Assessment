# Build from repository root: docker build -f deploy/Dockerfile -t hyhq-api:m1 .
# This image is optional; the Debian systemd templates use a Python venv.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system hyhq \
    && useradd --system --gid hyhq --home-dir /app hyhq
COPY --chown=hyhq:hyhq backend /app
RUN mkdir -p /app/var /app/staticfiles && chown -R hyhq:hyhq /app/var /app/staticfiles
USER hyhq
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "1", "--timeout", "30", "--access-logfile", "-"]
