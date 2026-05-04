FROM pyd4vinci/scrapling:latest AS base

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium --with-deps \
    || python -m playwright install chromium

COPY src ./src

ENV PYTHONUNBUFFERED=1
EXPOSE 8200

# pyd4vinci/scrapling base image sets ENTRYPOINT=["scrapling"]; reset so our CMDs run directly.
ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8200"]
