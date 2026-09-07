"""Generate the focused Google API contract from the FastAPI schemas."""

from pathlib import Path

import yaml
from fastapi import FastAPI
from services.api.app.api.google_authentication import router


def document() -> dict:
    app = FastAPI(title="Google 帳號與收容所加入審核", version="1.1.0")
    app.include_router(router)
    result = app.openapi()
    result["components"]["securitySchemes"] = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    result["security"] = [{"bearerAuth": []}]
    for path in result["paths"].values():
        for operation in path.values():
            for status in (401, 403, 404, 409, 410, 422, 429, 503):
                operation["responses"][str(status)] = {
                    "description": "去敏錯誤；429 包含 Retry-After",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["code", "message", "request_id"],
                                "properties": {
                                    field: {"type": "string"}
                                    for field in ("code", "message", "request_id")
                                },
                            }
                        }
                    },
                }
    return result


if __name__ == "__main__":
    destination = Path("specs/014-google-auth/contracts/openapi.yaml")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(document(), allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
