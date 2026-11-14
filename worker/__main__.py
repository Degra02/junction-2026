"""`python -m worker`: serve the stage worker with one process (models load once)."""

import logging
import os

import uvicorn


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    # Avoid WORKER_*: Kubernetes injects WORKER_PORT=tcp://... for the `worker` Service.
    uvicorn.run(
        "worker.app:app",
        host=os.environ.get("STAGE_WORKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("STAGE_WORKER_PORT", "8001")),
        workers=1,
    )


if __name__ == "__main__":
    main()
