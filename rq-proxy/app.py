# simple reverse proxy to rq-dashboard (forwards requests to rq_dashboard:9181)
from fastapi import FastAPI, Request, Response
import httpx
import os

app = FastAPI(title="rq-proxy")

RQ_DASH_URL = os.environ.get("RQ_DASHBOARD_URL", "http://rq_dashboard:9181")

@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(full_path: str, request: Request):
    url = f"{RQ_DASH_URL}/{full_path}"
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
            params=request.query_params
        )
    # Copy back response (you may want to filter hop-by-hop headers in production)
    response_headers = dict(resp.headers)
    return Response(content=resp.content, status_code=resp.status_code, headers=response_headers)
