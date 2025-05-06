import logging
import os
import random
import time

import httpx
import uvicorn
from fastapi import FastAPI, Response, Request
from opentelemetry.propagate import inject
from utils import PrometheusMiddleware, metrics, setting_otlp

APP_NAME = os.environ.get("APP_NAME", "fastapi-demo-app")
EXPOSE_PORT = os.environ.get("EXPOSE_PORT", 8000)
OTLP_GRPC_ENDPOINT = os.environ.get("OTLP_GRPC_ENDPOINT", "http://otel-collector:4319")
TARGET_ONE_SVC = os.environ.get("TARGET_ONE_SVC", "localhost:8000")
LOG_PATH = f"/logs/{APP_NAME}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
app = FastAPI()

# Setting metrics middleware
app.add_middleware(PrometheusMiddleware, app_name=APP_NAME)
app.add_route("/metrics", metrics)

# Setting OpenTelemetry exporter
setting_otlp(app, APP_NAME, OTLP_GRPC_ENDPOINT)


class EndpointFilter(logging.Filter):
    # Uvicorn endpoint access log filter
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("GET /metrics") == -1


# Filter out /endpoint
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())


@app.get("/")
async def read_root(request: Request):
    logging.info(f"Request headers: {request.headers}")
    logging.info("Hello World")
    logging.debug("Debugging log")
    logging.info("Info log")
    logging.warning("Hey, This is a warning!")
    logging.error("Oops! We have an Error. OK")
    return {"Hello": "World"}


@app.get("/cpu_io")
async def cpu_io():
    time.sleep(1)
    logging.info("io task")
    return "IO bound task finish!"


@app.get("/cpu_process")
async def cpu_process():
    for i in range(1000):
        n = i*i*i
    logging.info("cpu task")
    return "CPU bound task finish!"


@app.get("/random_status")
async def random_status(response: Response):
    response.status_code = random.choice([200, 200, 300, 400, 500])
    logging.info("random status")
    return {"path": "/random_status"}


@app.get("/thread_sleep")
async def thread_sleep(response: Response):
    time.sleep(random.randint(0, 5))
    logging.info("random sleep")
    return {"path": "/thread_sleep"}


@app.get("/error_test")
async def error_test(response: Response):
    logging.error("got error!!!!")
    raise ValueError("value error")


@app.get("/connect")
async def connect(response: Response):

    headers = {}
    inject(headers)  # inject trace info to header
    logging.critical(headers)

    async with httpx.AsyncClient() as client:
        await client.get("http://localhost:8000/", headers=headers,)
    async with httpx.AsyncClient() as client:
        await client.get(f"http://{TARGET_ONE_SVC}/cpu_io", headers=headers,)
    logging.info("connect Finished")
    return {"path": "/connect"}

if __name__ == "__main__":
    # update uvicorn access logger format
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s] - %(message)s"
    uvicorn.run(app, host="0.0.0.0", port=EXPOSE_PORT, log_config=log_config)
