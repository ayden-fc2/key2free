ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY nas/data_asset_service/app ./nas_service
RUN chmod -R a+rX /app/app /app/nas_service

EXPOSE 8080

CMD ["uvicorn", "nas_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
