"""TRELLIS.2 image -> 3D HTTP inference server (runs inside the container).

Exposes:
  GET  /health    -> {"ready": bool, "model": str}
  POST /generate  -> multipart image upload, returns a binary GLB

The TRELLIS pipeline is loaded once at startup. The model is taken from the
TRELLIS_MODEL env var (a HF repo id, or a mounted local path like /models/...).
"""
from __future__ import annotations

import io
import os
import tempfile

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image

MODEL = os.environ.get("TRELLIS_MODEL", "microsoft/TRELLIS.2-4B")
PORT = int(os.environ.get("TRELLIS_PORT", "8002"))
TEXTURE_SIZE = int(os.environ.get("TRELLIS_TEXTURE_SIZE", "2048"))

app = FastAPI(title="vibemcp-trellis")
_pipeline = None
_error = ""


def _load():
    """Load the TRELLIS.2 pipeline (called lazily on first use / startup)."""
    global _pipeline, _error
    if _pipeline is not None:
        return _pipeline
    try:
        from trellis2.pipelines import Trellis2ImageTo3DPipeline

        pipe = Trellis2ImageTo3DPipeline.from_pretrained(MODEL)
        try:
            pipe.cuda()
        except Exception:
            pass
        _pipeline = pipe
        _error = ""
    except Exception as exc:  # pragma: no cover - heavy/env dependent
        _error = str(exc)
        raise
    return _pipeline


@app.on_event("startup")
def _startup():
    try:
        _load()
    except Exception:
        # Keep the server up so /health can report the failure reason.
        pass


@app.get("/health")
def health():
    return {"ready": _pipeline is not None, "model": MODEL, "error": _error}


@app.post("/generate")
async def generate(
    file: UploadFile = File(...),
    seed: int = Form(42),
    pipeline_type: str = Form("1024_cascade"),
    preprocess_image: bool = Form(True),
    geometry_steps: int = Form(12),
    geometry_guidance: float = Form(7.5),
    texture_steps: int = Form(12),
    texture_guidance: float = Form(1.0),
    texture_size: int = Form(TEXTURE_SIZE),
):
    try:
        pipe = _load()
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": f"Modèle indisponible: {exc}"})

    import o_voxel

    data = await file.read()
    image = Image.open(io.BytesIO(data)).convert("RGBA")

    geom = {"steps": geometry_steps, "guidance_strength": geometry_guidance}
    tex = {"steps": texture_steps, "guidance_strength": texture_guidance}

    try:
        mesh = pipe.run(
            image,
            seed=seed,
            pipeline_type=pipeline_type,
            preprocess_image=preprocess_image,
            sparse_structure_sampler_params=geom,
            shape_slat_sampler_params=geom,
            tex_slat_sampler_params=tex,
        )[0]
        try:
            mesh.simplify(16777216)  # nvdiffrast vertex limit
        except Exception:
            pass

        out = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
        out.close()
        glb = o_voxel.postprocess.to_glb(
            vertices=mesh.vertices,
            faces=mesh.faces,
            attr_volume=mesh.attrs,
            coords=mesh.coords,
            attr_layout=mesh.layout,
            voxel_size=mesh.voxel_size,
            aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
            decimation_target=1000000,
            texture_size=texture_size,
            remesh=True,
            remesh_band=1,
            remesh_project=0,
            verbose=False,
        )
        glb.export(out.name, extension_webp=True)
        return FileResponse(out.name, media_type="model/gltf-binary", filename="model.glb")
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
