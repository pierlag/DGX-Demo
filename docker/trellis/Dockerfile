# TRELLIS.2 image -> 3D inference server (containerised).
#
# Building the native CUDA extensions here keeps the host venv clean and avoids
# the "externally-managed-environment" / sudo issues of the official setup.sh.
#
# BASE_IMAGE must provide CUDA + nvcc + a matching PyTorch for your GPU.
#   - x86_64 A100/H100      : pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel
#   - DGX Spark / GB10 ARM  : nvcr.io/nvidia/pytorch:25.04-py3  (NGC, multi-arch)
ARG BASE_IMAGE=nvcr.io/nvidia/pytorch:25.04-py3
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_INPUT=1 \
    OPENCV_IO_ENABLE_OPENEXR=1 \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    HF_HOME=/root/.cache/huggingface

# CUDA arch list for the native builds (override at build time if needed).
#   The base image's PyTorch supports arches up to 12.0 (Blackwell). GB10 is
#   sm_121: it runs the embedded 12.0 PTX via JIT forward-compat (+PTX), so do
#   NOT pass 12.1 here (PyTorch rejects it as "Unknown CUDA arch").
#   sm_90 = H100, sm_80 = A100, 12.0+PTX = Blackwell incl. GB10.
ARG TORCH_CUDA_ARCH_LIST="12.0+PTX"
ENV TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST}

RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential ninja-build cmake \
        libgl1 libglib2.0-0 libgomp1 \
        libx11-dev libgl1-mesa-dev libegl1-mesa-dev libglu1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone -b main --recursive https://github.com/microsoft/TRELLIS.2.git

WORKDIR /opt/TRELLIS.2

# --- Base Python dependencies -------------------------------------------------
RUN pip install --no-cache-dir \
        imageio imageio-ffmpeg tqdm easydict opencv-python-headless ninja \
        trimesh tensorboard pandas lpips zstandard kornia timm pybind11 \
        fastapi "uvicorn[standard]" python-multipart && \
    pip install --no-cache-dir \
        "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8"

# --- Native CUDA extensions (each isolated; build is long) --------------------
RUN pip install --no-cache-dir ./o-voxel --no-build-isolation
RUN mkdir -p /tmp/ext && \
    git clone -b v0.4.0 --recursive https://github.com/NVlabs/nvdiffrast.git /tmp/ext/nvdiffrast && \
    pip install --no-cache-dir /tmp/ext/nvdiffrast --no-build-isolation
RUN git clone -b renderutils --recursive https://github.com/JeffreyXiang/nvdiffrec.git /tmp/ext/nvdiffrec && \
    pip install --no-cache-dir /tmp/ext/nvdiffrec --no-build-isolation
RUN git clone --recursive https://github.com/JeffreyXiang/CuMesh.git /tmp/ext/CuMesh && \
    pip install --no-cache-dir /tmp/ext/CuMesh --no-build-isolation
RUN git clone --recursive https://github.com/JeffreyXiang/FlexGEMM.git /tmp/ext/FlexGEMM && \
    pip install --no-cache-dir /tmp/ext/FlexGEMM --no-build-isolation
# flash-attn is optional; the model falls back to a slower attention if absent.
RUN pip install --no-cache-dir flash-attn==2.7.3 --no-build-isolation || \
    echo "flash-attn build skipped (optional)"

# `transformers` is required by the TRELLIS.2 pipeline (image encoders). It is
# part of the official `--basic` install but is NOT bundled in the NGC image.
# Kept in its own layer (after the long CUDA builds) to preserve their cache.
RUN pip install --no-cache-dir transformers

# trellis2 lives at the repo root and is imported directly from there.
ENV PYTHONPATH=/opt/TRELLIS.2

COPY server.py /opt/server.py

# TRELLIS_MODEL may be a HF repo id or a mounted local path (/models/...).
ENV TRELLIS_MODEL=microsoft/TRELLIS.2-4B \
    TRELLIS_PORT=8002

EXPOSE 8002
CMD ["python", "/opt/server.py"]
