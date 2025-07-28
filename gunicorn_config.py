# Gunicorn configuration for production optimization
import multiprocessing
import os

# Server socket
bind = "0.0.0.0:10000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1  # Optimal worker count
worker_class = "sync"
worker_connections = 1000
timeout = 30
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
