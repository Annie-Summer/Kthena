FROM python:3.11-slim

WORKDIR /app
COPY adapter.py .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

USER nobody
CMD ["python", "-u", "adapter.py"]
