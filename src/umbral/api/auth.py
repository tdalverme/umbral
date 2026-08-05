"""Composition facade for identity routes."""

from umbral.api.routers.auth import configure_auth_routes, router

__all__ = ["configure_auth_routes", "router"]
