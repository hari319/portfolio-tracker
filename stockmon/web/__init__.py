"""Flask application factory."""

from __future__ import annotations

import logging

from flask import Flask

from ..paths import BASE_DIR, ensure_directories

logger = logging.getLogger(__name__)


def create_app(config: dict | None = None) -> Flask:
    ensure_directories()

    dist_dir = BASE_DIR / "frontend" / "dist"
    app = Flask(
        __name__,
        template_folder=str(dist_dir),
        static_folder=str(dist_dir),
        static_url_path="",
    )

    app.config.update(JSON_SORT_KEYS=False)
    if config:
        app.config.update(config)

    from .routes import bp  # imported here to avoid a circular import

    app.register_blueprint(bp)
    logger.info("Flask app created (static=%s)", app.static_folder)
    return app
