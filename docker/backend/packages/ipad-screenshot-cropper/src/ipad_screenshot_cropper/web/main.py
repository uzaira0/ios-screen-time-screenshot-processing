"""FastAPI application for iPad screenshot cropper service."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from .routes import router

app = FastAPI(
    title="iPad Screenshot Cropper API",
    description="Geometric cropping and device detection for iPad screenshots",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "ipad-screenshot-cropper",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
