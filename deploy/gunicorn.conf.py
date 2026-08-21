import multiprocessing

# Gunicorn configuration tailored for Django production
# Bind to all interfaces on port 8000
bind = "0.0.0.0:8000"

# Use gevent or gthread for better concurrency with async APIs
worker_class = "gthread"
threads = 4

# Workers calculation: 2 * num_cores + 1
workers = multiprocessing.cpu_count() * 2 + 1

# Timeouts and keeping connections alive
timeout = 120
keepalive = 5

# Maximum requests per worker to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-" # Stdout
errorlog = "-" # Stderr
loglevel = "info"
