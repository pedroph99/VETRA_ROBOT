"""Fábrica FastAPI: painel, imagens e módulos por domínio."""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from server.src.config import TEMPLATES_DIR
from server.src.inspections.router import router
from server.src.classification.router import router as classification_router

def make_app(state, classifier=None):
    app = FastAPI(title="VETRA · Inspeção fitossanitária")
    app.state.robot_state = state
    app.state.classifier = classifier
    app.mount("/images", StaticFiles(directory=state.data_dir / "images"), name="images")
    app.include_router(router)
    app.include_router(classification_router)

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(TEMPLATES_DIR / "dashboard.html", media_type="text/html")

    return app
