"""FastAPI application for PHI detection and removal service."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from phi_detector_remover.web.routes import router

# Create FastAPI app
app = FastAPI(
    title="PHI Detector & Remover",
    description="PHI detection and removal service using Microsoft Presidio and OCR",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "PHI Detector & Remover",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "phi_detector_remover.web.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
