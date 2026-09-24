"""Read-only local browser dashboard."""

from .server import StatePoller, create_dashboard_server, serve_dashboard

__all__ = ["StatePoller", "create_dashboard_server", "serve_dashboard"]
