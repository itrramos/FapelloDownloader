FROM python:3.11-slim

##
## Dockerfile for the FapelloDownloader web application
##
## This image uses the official python slim base and installs the
## dependencies declared in requirements.txt.  It then copies the
## application code into the image and starts the Flask web server on
## container startup.  The server listens on the port defined by the
## `PORT` environment variable (default 8080).

# Install basic build utilities and install python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first so Docker can cache package installation
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the image
COPY app app

# Default environment variables
ENV PYTHONUNBUFFERED=1

# Expose the internal port.  ZimaOS will map this port to a host port
EXPOSE 8080

# Start the application using the Python interpreter.  The application
# itself reads the PORT environment variable and falls back to 8080 if
# undefined.
CMD ["python", "app/app.py"]