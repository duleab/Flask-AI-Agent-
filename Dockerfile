FROM python:3.9-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create a writable directory for the SQLite database (required for some cloud providers)
RUN mkdir -p /app/instance && chmod 777 /app/instance

# Expose port 7860 (Standard for Hugging Face Spaces)
EXPOSE 7860

# Run the application using Gunicorn
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "-b", "0.0.0.0:7860", "app:app"]
