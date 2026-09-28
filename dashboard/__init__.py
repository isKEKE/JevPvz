"""Read-only local browser dashboard."""

from .server import StatePoller, TraceFileReader, create_dashboard_server, serve_dashboard

__all__ = ["StatePoller", "TraceFileReader", "create_dashboard_server", "serve_dashboard"]
