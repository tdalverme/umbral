"""Query the preview database state for the release conformance gate."""

from __future__ import annotations

import json
import os

import psycopg


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select version_num from alembic_version")
            revision = cursor.fetchone()[0]
            cursor.execute("select extname from pg_extension where extname in ('postgis', 'vector')")
            extensions = sorted(row[0] for row in cursor.fetchall())
    print(json.dumps({"revision": revision, "extensions": extensions}))


if __name__ == "__main__":
    main()
