import sys
sys.path.insert(0, "src")
import os, pathlib, json, hashlib, uuid, time
from datetime import datetime, timezone
os.environ["DATABASE_URL"] = "postgresql://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["UMBRAL_ENV"] = "local"
os.environ["UMBRAL_RELEASE_ID"] = "local-test"
os.environ["UMBRAL_RELEASE_MANIFEST"] = ".data/release-manifest.local.json"
os.environ["OBJECT_STORE_BACKEND"] = "filesystem"
os.environ["OBJECT_STORE_ROOT"] = ".data/objects"
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
os.environ["UMBRAL_API_BASE_URL"] = "http://localhost:8000"

from sqlalchemy import create_engine
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

raw = pathlib.Path(".data/caballito.json").read_bytes()
data = json.loads(raw)
print(f"records {len(data['records'])}")

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

# check existing
existing = ingestion.runs.get_by_identity("zonaprop", request.batch_key)
if existing:
    print(f"already exists {existing.run_id} state={existing.state}")
    run_id = existing.run_id
else:
    snapshot = ingestion.submit(request)
    run_id = snapshot.run_id
    print(f"submitted {run_id} state={snapshot.state}")
    # the submit created pending run with job_execution_id maybe None because job_runtime is None
    # we need to manually set execution and process
    # fetch run
    run = ingestion.runs.get(run_id)
    print(f"run {run.run_id} state {run.state} job_exec {run.job_execution_id}")
    # If job_execution_id is None, we need to assign one to process
    if run.job_execution_id is None:
        # Use the run_id as execution id for direct process, or generate new
        # The process method expects execution_id to find run via find_by_job_execution
        # Let's patch: set job_execution_id and save
        new_exec = uuid.uuid4()
        run.job_execution_id = new_exec
        ingestion.runs.save(run)
        print(f"assigned execution {new_exec}")
    # Now process
    try:
        result = ingestion.process(run.job_execution_id)
        print(f"processed {result.run_id} state={result.state} total={result.total_records} accepted={result.accepted}")
    except Exception as e:
        import traceback
        traceback.print_exc()

# Now silver
from umbral.infrastructure.silver.composition import build_normalize_service
silver = build_normalize_service(
    session_factory=session_provider.session_factory,
    geocoding_enabled=True,
    geocoding_endpoint="https://nominatim.openstreetmap.org",
    geocoding_cache_size=512,
    geocoding_rate_limit=1.0,
)

# get the run again
run = ingestion.runs.get(run_id)
print(f"final run state {run.state} accepted {run.accepted}")

if run.state == "succeeded":
    try:
        summary = silver.process(run_id)
        print(f"silver summary run_id={summary.run_id} total={summary.total_snapshots} inserted={summary.listings_inserted} skipped={summary.skipped}")
    except Exception as e:
        import traceback
        traceback.print_exc()
else:
    print("run not succeeded, cannot silver")
