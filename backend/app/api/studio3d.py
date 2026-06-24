"""Studio 3D API: text->image, image upload, and image->3D (TRELLIS.2).

Endpoints under ``/api/studio3d``:
  GET  /status                      - availability + load state of both models
  POST /image-gen/load              - warm up the text->image model
  POST /trellis/load                - warm up the TRELLIS.2 pipeline
  POST /text-to-image               - {prompt, seed?} -> background job (image)
  POST /upload                      - multipart image -> stored asset
  POST /generate                    - {image_name} -> background job (mesh/GLB)
  GET  /job?job_id=                 - poll a background job
  GET  /jobs                        - list recent jobs (resume after navigation)
  GET  /history                     - list generated images/meshes
  DELETE /file/{name}               - delete a generated asset + history entry
  GET  /file/{name}                 - serve a generated image/GLB asset
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.services.studio3d import studio_manager

router = APIRouter(prefix="/api/studio3d", tags=["studio3d"])

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_MEDIA = {
    ".glb": "model/gltf-binary",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class TextToImageRequest(BaseModel):
    prompt: str
    seed: int | None = None
    steps: int = 1
    guidance: float = 0.0
    width: int = 512
    height: int = 512
    negative_prompt: str = ""


class GenerateRequest(BaseModel):
    image_name: str
    seed: int = 42
    pipeline_type: str = "1024_cascade"
    preprocess_image: bool = True
    geometry_steps: int = 12
    geometry_guidance: float = 7.5
    texture_steps: int = 12
    texture_guidance: float = 1.0
    texture_size: int = 2048


class RuntimeRequest(BaseModel):
    runtime: str


class PreviewRequest(BaseModel):
    name: str
    image: str  # data URL: "data:image/png;base64,..."


@router.get("/status")
def status():
    return studio_manager.status()


@router.post("/image-gen/load")
def load_image_gen():
    return studio_manager.load_image_gen()


@router.post("/trellis/load")
def load_trellis():
    return studio_manager.load_trellis()


@router.post("/trellis/runtime")
def set_trellis_runtime(req: RuntimeRequest):
    return studio_manager.set_trellis_runtime(req.runtime)


@router.post("/trellis/container/build")
def build_trellis_container():
    return studio_manager.build_trellis_container()


@router.post("/trellis/container/start")
def start_trellis_container():
    return studio_manager.start_trellis_container()


@router.post("/trellis/container/stop")
def stop_trellis_container():
    return studio_manager.stop_trellis_container()


@router.post("/text-to-image")
def text_to_image(req: TextToImageRequest):
    if not req.prompt.strip():
        return {"ok": False, "message": "Prompt vide."}
    params = {
        "steps": req.steps,
        "guidance": req.guidance,
        "width": req.width,
        "height": req.height,
        "negative_prompt": req.negative_prompt,
    }
    job = studio_manager.submit_image(req.prompt.strip(), req.seed, params=params)
    return {"ok": True, "job": job.to_dict()}


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    suffix = ""
    if file.filename and "." in file.filename:
        suffix = "." + file.filename.rsplit(".", 1)[-1].lower()
    if suffix not in _MEDIA:
        suffix = ".png"
    name = f"upload_{uuid.uuid4().hex[:12]}{suffix}"
    dest = settings.studio_assets_dir / name
    data = await file.read()
    dest.write_bytes(data)
    studio_manager.register_image(name)
    return {"ok": True, "image_name": name, "image_url": f"/api/studio3d/file/{name}"}


@router.post("/generate")
def generate(req: GenerateRequest):
    name = req.image_name
    if not _SAFE_NAME.match(name) or not (settings.studio_assets_dir / name).exists():
        return {"ok": False, "message": "Image source introuvable."}
    params = req.model_dump(exclude={"image_name"})
    job = studio_manager.submit_mesh(name, params=params)
    return {"ok": True, "job": job.to_dict()}


@router.get("/job")
def job(job_id: str):
    j = studio_manager.get_job(job_id)
    return {"job": j.to_dict() if j else None}


@router.get("/jobs")
def jobs():
    return {"jobs": studio_manager.list_jobs()}


@router.get("/queue")
def queue():
    return {"jobs": studio_manager.queue()}


@router.get("/history")
def history():
    return {"items": studio_manager.history()}


@router.post("/preview")
def set_preview(req: PreviewRequest):
    if not _SAFE_NAME.match(req.name):
        return {"ok": False, "message": "Nom invalide."}
    return studio_manager.set_preview(req.name, req.image)


@router.delete("/file/{name}")
def delete_file(name: str):
    if not _SAFE_NAME.match(name):
        return {"ok": False, "message": "Nom invalide."}
    return studio_manager.delete_asset(name)


@router.get("/file/{name}")
def file(name: str):
    if not _SAFE_NAME.match(name):
        return {"ok": False, "message": "Nom invalide."}
    path = (settings.studio_assets_dir / name).resolve()
    if settings.studio_assets_dir.resolve() not in path.parents or not path.exists():
        return {"ok": False, "message": "Fichier introuvable."}
    suffix = path.suffix.lower()
    media = _MEDIA.get(suffix, "application/octet-stream")
    return FileResponse(str(path), media_type=media, filename=name)
