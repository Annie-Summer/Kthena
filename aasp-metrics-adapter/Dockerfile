FROM python:3.11-slim

WORKDIR /app
COPY adapter.py .
# Ensure non-root can read the app (avoids Errno 13 when USER is nobody).
RUN chmod 644 /app/adapter.py && chmod 755 /app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Run as non-root, but with readable app files.
USER nobody
CMD ["python", "-u", "/app/adapter.py"]