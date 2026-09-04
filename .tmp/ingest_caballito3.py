import sys
sys.path.insert(0, "src")
import os, pathlib, json, hashlib, uuid
from sqlalchemy import create_engine, text

db_url = "postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
engine = create_engine(db_url)
batch_key = hashlib.sha256(pathlib.Path(".data/caballito.json").read_bytes()).hexdigest()
print(batch_key)
with engine.connect() as c:
    r = c.execute(text("select id, state, job_execution_id, batch_key, source_id, file_name from import_runs where batch_key=:k"), {"k": batch_key})
    for row in r:
        print(row)
        run_id = row[0]
        job_exec = row[2]
    # if no job_execution_id, create one
    if job_exec is None:
        new_exec = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(text("update import_runs set job_execution_id=:jid where id=:rid"), {"jid": new_exec, "rid": str(run_id)})
        print(f"updated job_execution_id to {new_exec}")
        job_exec = new_exec
    print(f"run_id {run_id} job_exec {job_exec}")

# now try ingestion process via service with that exec
import os
os.environ["DATABASE_URL"] = "postgresql://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["UMBRAL_ENV"] = "local"
os.environ["UMBRAL_RELEASE_ID"] = "local-test"
os.environ["UMBRAL_RELEASE_MANIFEST"] = ".data/release-manifest.local.json"
os.environ["OBJECT_STORE_BACKEND"] = "filesystem"
os.environ["OBJECT_STORE_ROOT"] = ".data/objects"
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
os.environ["UMBRAL_API_BASE_URL"] = "http://localhost:8000"

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

# need uuid
import uuid as uuidlib
exec_uuid = uuidlib.UUID(job_exec)
try:
    result = ingestion.process(exec_uuid)
    print(f"processed {result.run_id} state={result.state} total={result.total_records} accepted={result.accepted} quarantined={result.quarantined}")
except Exception as e:
    import traceback
    traceback.print_exc()
