import os

port = os.environ.get("PORT", "8000")
bind = f"0.0.0.0:{port}"
limit_request_line = 8190
limit_request_field_size = 0
workers = 3
worker_class = "gthread"
threads = 4
timeout = 120
