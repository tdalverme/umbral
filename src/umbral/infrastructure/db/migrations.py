"""Metadata entry point consumed by Alembic and migration checks."""

from __future__ import annotations

from sqlalchemy import MetaData

from umbral.infrastructure.db import models as _models
from umbral.infrastructure.db.base import metadata

del _models


def expected_schema() -> MetaData:
    """Return the imported foundation metadata, without opening a database."""

    return metadata
