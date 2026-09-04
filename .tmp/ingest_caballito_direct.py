import sys
sys.path.insert(0, "src")
import os, pathlib, json, hashlib, uuid
from datetime import datetime, timezone
import sys

# Use local env for DB but point to Railway
os.environ["DATABASE_URL"] = "postgresql://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from umbral.infrastructure.db.session import SessionProvider
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
# Build repos
from umbral.infrastructure.db.repositories.imports import SqlAlchemyImportRunRepository, SqlAlchemyRawSnapshotRepository
from umbral.infrastructure.db.repositories.silver import SqlAlchemyCanonicalPropertyRepository, SqlAlchemySilverListingRepository, SqlAlchemyChangeRepository, SqlAlchemyDedupeLinkRepository
from umbral.infrastructure.ingestion.contract_loader import load_contract_v2
from umbral.infrastructure.silver.contract_loader import load_silver_schema, load_dedupe_policy
from umbral.application.ingestion.contracts import SourceIdentity, RawListingSnapshot
from umbral.application.ingestion.import_contract import validate_record
from umbral.application.silver.silver_schema import normalize_snapshot
from umbral.application.silver.service import NormalizeRunService
from umbral.infrastructure.object_store.factory import build_object_store
from umbral.application.ingestion.contracts import ImportBatchRequest

raw_bytes = pathlib.Path(".data/caballito.json").read_bytes()
envelope = json.loads(raw_bytes)
records = envelope["records"]
print(f"records to ingest {len(records)}")

# Create import run directly via repo
from umbral.domain.audit import AuditActor
run_repo = SqlAlchemyImportRunRepository(session_provider.session_factory)
snap_repo = SqlAlchemyRawSnapshotRepository(session_provider.session_factory)
canon_repo = SqlAlchemyCanonicalPropertyRepository(session_provider.session_factory)
silver_repo = SqlAlchemySilverListingRepository(session_provider.session_factory)
change_repo = SqlAlchemyChangeRepository(session_provider.session_factory)
link_repo = SqlAlchemyDedupeLinkRepository(session_provider.session_factory)

contract = load_contract_v2()
schema = load_silver_schema()
dedupe = load_dedupe_policy()

batch_key = hashlib.sha256(raw_bytes).hexdigest()
file_sha = batch_key
run_id = uuid.uuid4()
now = datetime.now(timezone.utc)
source = SourceIdentity("zonaprop", "manual-v1", "2")

# Check if already exists
existing = run_repo.get_by_identity("zonaprop", batch_key)
if existing:
    print(f"run already exists {existing.run_id} state {existing.state}, deleting snapshots and run")
    # delete existing run and snapshots? For now reuse
    run_id = existing.run_id
else:
    # Create run
    run = run_repo.create(
        run_id=run_id,
        source=source,
        batch_key=batch_key,
        file_format="json",
        file_name="caballito.json",
        file_sha256=file_sha,
        file_size_bytes=len(raw_bytes),
        raw_storage_key=f"objects/raw/{file_sha}",
        job_execution_id=None,
        correlation_id=uuid.uuid4(),
        actor_kind="operator",
        actor_id="ops-cli",
        now=now,
    )
    print(f"created run {run.run_id}")

# Store snapshots (if not already)
# First, check existing snapshots for this run
existing_snaps = snap_repo.list_for_run(run_id)
print(f"existing snaps {len(existing_snaps)}")
if len(existing_snaps) == 0:
    inserted = 0
    for payload in records:
        result = validate_record(payload, contract)
        if not result.valid:
            print(f"invalid {payload.get('external_id')}: {result.issues}")
            continue
        snap = RawListingSnapshot(
            snapshot_id=uuid.uuid4(),
            run_id=run_id,
            source=source,
            external_id=str(payload["external_id"]),
            payload=payload,
            content_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            content_type="application/json",
            size_bytes=len(json.dumps(payload).encode()),
            published_at=None,
            captured_at=now,
        )
        snap_repo.insert(snap)
        inserted += 1
    print(f"inserted {inserted} snapshots")
    # Update run counts
    run = run_repo.get(run_id)
    run.total_records = len(records)
    run.accepted = inserted
    run.quarantined = len(records) - inserted
    run.state = "succeeded"
    run.finished_at = now
    run.updated_at = now
    run_repo.save(run)
    print(f"updated run to succeeded")
else:
    run = run_repo.get(run_id)
    if run.state != "succeeded":
        run.state = "succeeded"
        run.finished_at = now
        run.updated_at = now
        run_repo.save(run)

# Now normalize with geocoding enabled
from umbral.infrastructure.silver.composition import build_normalize_service
silver_service = build_normalize_service(
    session_factory=session_provider.session_factory,
    geocoding_enabled=True,
    geocoding_endpoint="https://nominatim.openstreetmap.org",
    geocoding_cache_size=512,
    geocoding_rate_limit=1.0,
)

summary = silver_service.process(run_id)
print(f"silver summary: total={summary.total_snapshots} inserted={summary.listings_inserted} skipped={summary.skipped} changes={summary.changes_emitted} links={summary.links_created}")

# Verify
from sqlalchemy import text, create_engine
engine = create_engine("postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway")
with engine.connect() as c:
    print("silver total", c.execute(text("select count(*) from silver_listings")).scalar())
    for r in c.execute(text("select neighborhood, geo_precision, count(*) from silver_listings group by 1,2 order by count(*) desc")):
        print(r)
