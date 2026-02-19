"""Gunicorn configuration for production deployment."""

import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('EVIDENTIA_PORT', '8000')}"

# Worker processes
workers = int(os.getenv("EVIDENTIA_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"
worker_tmp_dir = "/dev/shm"

# Timeouts
timeout = 120           # Worker timeout for long-running agent queries
graceful_timeout = 30   # Time to finish in-flight requests on shutdown
keepalive = 5

# Logging
accesslog = "-"         # stdout
errorlog = "-"          # stderr
loglevel = os.getenv("EVIDENTIA_LOG_LEVEL", "info").lower()

# Process naming
proc_name = "evidentia"

# Restart workers after N requests (prevent memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Preload app for faster worker startup (shares memory)
preload_app = True
