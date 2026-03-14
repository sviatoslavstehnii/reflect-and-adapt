FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .

# BUG 1: no CMD or ENTRYPOINT — container starts and immediately exits
# BUG 2: app binds to 127.0.0.1 (localhost inside container) not 0.0.0.0
#         so even after fixing CMD, it won't be reachable from outside
EXPOSE 5000
