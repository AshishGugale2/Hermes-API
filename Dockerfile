FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
RUN pip install . && useradd --create-home --uid 10001 hermes
USER hermes
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
