"""API routes for Docker container management and monitoring."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.docker_manager import docker_manager


router = APIRouter(prefix="/api/docker", tags=["docker"])


class ContainerResponse(BaseModel):
    id: str
    name: str
    image: str
    status: str
    created: str
    cpu_percent: float | None = None
    memory_usage_mb: float | None = None
    memory_limit_mb: float | None = None
    memory_percent: float | None = None


@router.get("/containers")
async def list_containers(all_: bool = True) -> list[ContainerResponse]:
    """List all Docker containers with optional stats."""
    containers = docker_manager.list_containers(all_=all_)
    result = []
    
    for cont in containers:
        stats = None
        # `docker ps` reports running containers with a status like "Up 3 hours".
        if cont.status.lower().startswith("up"):
            stats = docker_manager.get_container_stats(cont.id)
        
        result.append(ContainerResponse(
            id=cont.id,
            name=cont.name,
            image=cont.image,
            status=cont.status,
            created=cont.created,
            cpu_percent=stats.cpu_percent if stats else None,
            memory_usage_mb=stats.memory_usage_mb if stats else None,
            memory_limit_mb=stats.memory_limit_mb if stats else None,
            memory_percent=stats.memory_percent if stats else None,
        ))
    
    return result


@router.post("/containers/{container_id}/start")
async def start_container(container_id: str) -> dict[str, str]:
    """Start a stopped container."""
    success, msg = docker_manager.start_container(container_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


@router.post("/containers/{container_id}/stop")
async def stop_container(container_id: str) -> dict[str, str]:
    """Stop a running container."""
    success, msg = docker_manager.stop_container(container_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


@router.get("/containers/{container_id}/config")
async def get_container_config(container_id: str) -> dict:
    """Get full container configuration."""
    config = docker_manager.inspect_container(container_id)
    if not config:
        raise HTTPException(status_code=404, detail="Container not found")
    return config
