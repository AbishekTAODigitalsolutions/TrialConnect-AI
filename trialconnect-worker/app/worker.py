from celery import Celery

app = Celery("trialconnect_worker", broker="redis://task-broker:6379/0", backend="redis://task-broker:6379/0")


@app.task
def heartbeat() -> str:
    return "worker-ready"
