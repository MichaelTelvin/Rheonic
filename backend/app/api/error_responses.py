# Shared API error response helpers.
from fastapi.responses import JSONResponse


def build_error_response(status_code: int, code: str, message: str) -> JSONResponse:
    # Build a standardized API error response payload.
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


def default_code_for_status(status_code: int) -> str:
    # Map HTTP status to stable API error code.
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        500: "internal_error",
    }.get(status_code, "request_error")
