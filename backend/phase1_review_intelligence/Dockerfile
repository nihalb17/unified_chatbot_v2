FROM python:3.10-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port (Render sets $PORT, default to 8000 for local)
ENV PORT=8000
EXPOSE $PORT

# Command to run FastAPI, dynamically binding to $PORT
CMD uvicorn api:app --host 0.0.0.0 --port $PORT
