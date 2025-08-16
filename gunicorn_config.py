# Gunicorn configuration for production optimization
import multiprocessing
import os

# Server socket - Use PORT environment variable provided by Render
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"
backlog = 2048

# Worker processes - Reduce for faster startup on Render
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)  # Cap at 4 workers
worker_class = "sync"
worker_connections = 1000
timeout = 120  # Increase timeout for Render
keepalive = 3

# Restart workers
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Performance tuning
worker_tmp_dir = "/dev/shm"  # Use RAM for tmp files
