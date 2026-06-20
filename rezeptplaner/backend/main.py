import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

ingress_path = os.environ.get("INGRESS_PATH", "")

app = FastAPI(root_path=ingress_path)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
