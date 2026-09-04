import sys
sys.path.insert(0, "src")
import os, pathlib, json, hashlib, uuid
from datetime import datetime, timezone
os.environ["DATABASE_URL"] = "postgresql://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
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
from umbral.infrastructure.db.repositories.imports import SqlAlchemyImportRunRepository, SqlAlchemyRawSnapshotRepository
from umbral.infrastructure.ingestion.contract_loader import load_contract_v2
from umbral.application.ingestion.contracts import SourceIdentity, RawListingSnapshot
from umbral.application.ingestion.import_contract import validate_record
from umbral.infrastructure.silver.composition import build_normalize_service

raw_bytes = pathlib.Path(".data/flores.json").read_bytes()
records = json.loads(raw_bytes)["records"]
print(f"records {len(records)}")
batch_key = hashlib.sha256(raw_bytes).hexdigest()
run_repo = SqlAlchemyImportRunRepository(session_provider.session_factory)
snap_repo = SqlAlchemyRawSnapshotRepository(session_provider.session_factory)
contract = load_contract_v2()
source = SourceIdentity("zonaprop", "manual-v1", "2")
existing = run_repo.get_by_identity("zonaprop", batch_key)
if existing:
    print(f"exists {existing.run_id}")
    run_id = existing.run_id
else:
    run_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    run = run_repo.create(run_id=run_id, source=source, batch_key=batch_key, file_format="json", file_name="flores.json", file_sha256=batch_key, file_size_bytes=len(raw_bytes), raw_storage_key=f"objects/raw/{batch_key}", job_execution_id=None, correlation_id=uuid.uuid4(), actor_kind="operator", actor_id="ops-cli", now=now)
    print(f"created {run_id}")
    inserted=0
    for payload in records:
        if not validate_record(payload, contract).valid:
            continue
        snap = RawListingSnapshot(snapshot_id=uuid.uuid4(), run_id=run_id, source=source, external_id=str(payload["external_id"]), payload=payload, content_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), content_type="application/json", size_bytes=len(json.dumps(payload).encode()), published_at=None, captured_at=now)
        snap_repo.insert(snap)
        inserted+=1
    print(f"inserted {inserted}")
    run = run_repo.get(run_id)
    run.total_records=len(records); run.accepted=inserted; run.quarantined=len(records)-inserted; run.state="succeeded"; run.finished_at=now; run.updated_at=now
    run_repo.save(run)

# silver with higher rate to try to get some geocoded
silver = build_normalize_service(session_factory=session_provider.session_factory, geocoding_enabled=True, geocoding_endpoint="https://nominatim.openstreetmap.org", geocoding_cache_size=512, geocoding_rate_limit=5.0)
summary = silver.process(run_id)
print(f"silver inserted={summary.listings_inserted} skipped={summary.skipped}")
from sqlalchemy import create_engine, text
engine = create_engine("postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway")
with engine.connect() as c:
    for r in c.execute(text("select neighborhood, geo_precision, count(*) from silver_listings group by 1,2 order by count(*) desc")):
        print(r)
    print("total", c.execute(text("select count(*) from silver_listings")).scalar())
    print("null", c.execute(text("select count(*) from silver_listings where geometry is null")).scalar())
