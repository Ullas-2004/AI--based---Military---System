# Flask API + ML/vision runtime.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgl/libglib are needed by OpenCV even in headless mode.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Dependencies first so code edits do not invalidate the wheel cache.
COPY api/requirements.txt api/requirements-dev.txt ./api/
# CPU-only torch: the default wheels pull ~2.5 GB of CUDA that a server without
# a GPU will never use.
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    -r api/requirements-dev.txt

COPY api/ ./api/

# Train the threat model at build time so the image ships ready to serve.
RUN python api/train_threat_model.py

# Run as a non-root user.
RUN useradd --create-home --uid 10001 aegis \
 && chown -R aegis:aegis /app
USER aegis

EXPOSE 5332

# waitress rather than the Flask dev server. Threads matter here: the SSE
# stream holds a thread per connected client.
CMD ["python", "-m", "waitress", "--host=0.0.0.0", "--port=5332", \
     "--threads=16", "--call", "api.app:create_app"]
