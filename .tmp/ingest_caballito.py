import sys
sys.path.insert(0, "src")
import os
os.environ["DATABASE_URL"] = "postgresql://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
os.environ["REDIS_URL"] = "redis://default:dummy@localhost:6379/0"
os.environ["UMBRAL_ENV"] = "local"
os.environ["UMBRAL_RELEASE_ID"] = "local-test"
os.environ["UMBRAL_RELEASE_MANIFEST"] = ".data/release-manifest.local.json"
os.environ["OBJECT_STORE_BACKEND"] = "filesystem"
os.environ["OBJECT_STORE_ROOT"] = ".data/objects"
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
os.environ["UMBRAL_API_BASE_URL"] = "http://localhost:8000"
# need to bypass redis for submit? The submit will try to enqueue via redis, but we can set fake redis? Let's inspect ingestion submit without redis.
# Actually build_process_dependencies requires redis connection. We can monkey patch to avoid.
# Alternative: directly insert via ingestion service without queue, using direct DB.

import pathlib, json, hashlib, uuid
from datetime import datetime, timezone

# Load file
raw = pathlib.Path(".data/caballito.json").read_bytes()
print("raw len", len(raw))
data = json.loads(raw)
print("records", len(data["records"]))

# Use direct approach: call ingestion service submit but with fake queue
# Let's try to build only ingestion + silver without full composition
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.object_store.factory import build_object_store
from umbral.infrastructure.ingestion.composition import build_ingestion_service
from umbral.infrastructure.config.settings import Settings

settings = Settings.from_environment({
    "UMBRAL_ENV": "local",
    "UMBRAL_RELEASE_ID": "local-test",
    "UMBRAL_RELEASE_MANIFEST": ".data/release-manifest.local.json",
    "DATABASE_URL": os.environ["DATABASE_URL"],
    "REDIS_URL": "redis://localhost:6379/0",
    "OBJECT_STORE_BACKEND": "filesystem",
    "OBJECT_STORE_ROOT": ".data/objects",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
    "UMBRAL_API_BASE_URL": "http://localhost:8000",
})

session_provider = SessionProvider(settings.database_url)
object_store = build_object_store(settings)
ingestion = build_ingestion_service(session_factory=session_provider.session_factory, object_store=object_store)

from umbral.application.ingestion.contracts import ImportBatchRequest, SourceIdentity
from umbral.domain.audit import AuditActor

request = ImportBatchRequest(
    source=SourceIdentity("zonaprop", "manual-v1", "2"),
    batch_key=hashlib.sha256(raw).hexdigest(),
    file_format="json",
    file_name="caballito.json",
    raw=raw,
    actor=AuditActor(kind="operator", id="ops-cli"),
    correlation_id=uuid.uuid4(),
)

# Need to set job_runtime to None? The ingestion service will try to enqueue; if redis not available, it may fail but still create import_run and snapshots? Let's check.
# We can set ingestion.job_runtime = None to skip enqueue, then manually trigger silver.
# Inspect ingestion service
print("ingestion service", ingestion)

# Try submit
try:
    snapshot = ingestion.submit(request)
    print("submitted", snapshot)
    print(f"run_id={snapshot.run_id} state={snapshot.state} total={snapshot.total_records} accepted={snapshot.accepted}")
except Exception as e:
    import traceback
    traceback.print_exc()

# Now trigger silver normalization directly, bypassing queue, using the same settings with geocoding enabled
from umbral.infrastructure.silver.composition import build_normalize_service

# Build with geocoding enabled like Railway now
silver = build_normalize_service(
    session_factory=session_provider.session_factory,
    geocoding_enabled=True,
    geocoding_endpoint="https://nominatim.openstreetmap.org",
    geocoding_cache_size=512,
    geocoding_rate_limit=1.0,
)

# Process the run we just created
if 'snapshot' in locals():
    try:
        summary = silver.process(snapshot.run_id)
        print("silver summary", summary)
    except Exception as e:
        import traceback
        traceback.print_exc()
