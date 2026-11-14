"""`python -m worker`: serve the stage worker with one process (models load once)."""

import logging
import os

import uvicorn

if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    uvicorn.run(
        "worker.app:app",
        host=os.environ.get("WORKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("WORKER_PORT", "8001")),
        workers=1,
    )
