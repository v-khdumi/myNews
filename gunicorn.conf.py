bind = "0.0.0.0:8000"
workers = 1
threads = 4
timeout = 120
accesslog = "-"
errorlog = "-"


def post_worker_init(worker):
    from server import app, start_scheduler
    start_scheduler(app)
