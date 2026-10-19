FROM python:3.12.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /data && chown app:app /data
COPY --chown=app:app repere ./repere
COPY --chown=app:app static ./static
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app LICENSE README.md ./
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=3)" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "30", "--access-logfile", "-", "repere.web:create_app()"]
