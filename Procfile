web: uvicorn app.api:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 75 --timeout-graceful-shutdown 10
worker: python -m app.core.monitor

