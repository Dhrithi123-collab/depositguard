from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import public_router, router
from app.core.config import get_settings
from app.services.database import initialize_database
from app.services.workflow import WorkflowConfigurationError
from app.services.storage import (
    StorageConfigurationError,
    StorageUnavailable,
    UploadPolicyError,
)
from app.services.graph import GraphPolicyError
from app.services.priority import PriorityConfigurationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("depositguard.api")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled API error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            {"error": {"code": "validation_error", "message": "Request validation failed.", "details": exc.errors()}}
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": message}},
        headers=exc.headers,
    )


@app.exception_handler(WorkflowConfigurationError)
async def workflow_configuration_exception_handler(_: Request, exc: WorkflowConfigurationError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "workflow_configuration_unavailable", "message": str(exc)}},
    )


@app.exception_handler(UploadPolicyError)
@app.exception_handler(StorageConfigurationError)
async def upload_configuration_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "upload_configuration_unavailable", "message": str(exc)}},
    )


@app.exception_handler(GraphPolicyError)
async def graph_policy_exception_handler(_: Request, exc: GraphPolicyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "graph_policy_unavailable", "message": str(exc)}},
    )


@app.exception_handler(PriorityConfigurationError)
async def priority_configuration_exception_handler(_: Request, exc: PriorityConfigurationError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "priority_configuration_unavailable", "message": str(exc)}},
    )


@app.exception_handler(StorageUnavailable)
async def storage_exception_handler(_: Request, exc: StorageUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "private_storage_unavailable", "message": str(exc)}},
    )


app.include_router(public_router, prefix=settings.api_v1_prefix)
app.include_router(router, prefix=settings.api_v1_prefix)
