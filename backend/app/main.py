"""FastAPI application entry point.

Route modules for endpoints E1 to E11 are registered here as they are
implemented. Until then this application exposes only the service metadata and
health endpoints, which exist so the deployment and the database connection can
be verified before any feature depends on them.
"""

from app.api.routes import health
from app.config import get_settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

SCOPE_STATEMENT = (
    "This system reports inconsistency between an application's Google Play "
    "Data Safety declaration and its privacy policy text. It does not "
    "determine legality, regulatory compliance, developer intent, or whether "
    "an application is malicious."
)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Cross-Source Privacy Disclosure Consistency Auditor",
        description=SCOPE_STATEMENT,
        version="0.1.0",
    )

    # The SPA is served from a different origin during development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(health.router)

    @app.get("/api/meta/scope", tags=["meta"])
    def scope() -> dict[str, str]:
        """Scope statement shown by the frontend (F-26). Served from one place
        so the wording cannot drift between the API and the interface."""
        return {"scope": SCOPE_STATEMENT}

    _mount_frontend(app, settings)

    app.state.settings = settings
    return app


def _mount_frontend(app: FastAPI, settings) -> None:
    """Serve the built SPA from this same process when it is present.

    This is what keeps the deployment at the three containers the approved
    design specifies, instead of adding a fourth for a web server. During
    development STATIC_DIR is unset and Vite serves the SPA, so nothing is
    mounted and the API runs alone.

    The mount is added last so that every /api route takes precedence over the
    catch-all, and html=True makes client-side routes resolve to index.html.
    """
    directory = settings.static_dir
    if directory is None:
        return
    if not directory.is_dir():
        # Say so rather than failing silently: a missing build directory in a
        # container means the frontend build stage did not produce output.
        app.state.static_warning = f"STATIC_DIR is set to {directory} but it does not exist."
        return

    app.mount("/", StaticFiles(directory=str(directory), html=True), name="frontend")


app = create_app()
