FROM python:3.11-slim

LABEL description="TBS Grading Dashboard — FastAPI REST Backend"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api_server.py .

RUN useradd --no-create-home --shell /bin/false api_user
USER api_user

EXPOSE 8000

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
