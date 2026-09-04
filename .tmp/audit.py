import os
os.environ.setdefault("PYTHONPATH", "src")
import sys
sys.path.insert(0, "src")
from sqlalchemy import create_engine, text

db_url = "postgresql+psycopg://umbral:local@localhost:5432/umbral"
engine = create_engine(db_url)
with engine.connect() as c:
    def q(sql, params=None):
        try:
            r = c.execute(text(sql), params or {})
            return r
        except Exception as e:
            print(f"ERR {sql[:60]}: {e}")
            return None

    print("=== LISTINGS ===")
    r = q("select count(*) from listings")
    if r: print("total", r.scalar())
    r = q("select count(*) from listings where latitude is not null and longitude is not null")
    if r: print("with coords", r.scalar())
    r = q("select count(*) from listings where latitude is null or longitude is null")
    if r: print("without coords", r.scalar())
    r = q("select count(*) from listings where neighborhood ilike '%palermo%'")
    if r: print("palermo total", r.scalar())
    r = q("select count(*) from listings where neighborhood ilike '%palermo%' and (latitude is null or longitude is null)")
    if r: print("palermo without coords", r.scalar())
    r = q("select geocoding_level, count(*) from listings group by geocoding_level order by count(*) desc")
    if r:
        for row in r:
            print("geocoding_level", row)
    r = q("select status, count(*) from listings group by status")
    if r:
        for row in r: print("status", row)
    r = q("select source, count(*) from listings group by source")
    if r:
        for row in r: print("source", row)
    print("\n=== PALERMO SAMPLE ===")
    r = q("select id, source_id, address, neighborhood, latitude, longitude, geocoding_level, raw_payload->>'address' as raw_addr from listings where neighborhood ilike '%palermo%' limit 10")
    if r:
        for row in r:
            print(row)
    print("\n=== BRONZE / RAW ===")
    r = q("select count(*) from bronze_listings")
    if r: print("bronze", r.scalar())
    else:
        r2 = q("select count(*) from raw_listings")
        if r2: print("raw", r2.scalar())
    print("\n=== SILVER? ===")
    # try silver tables
    for tbl in ["silver_listings", "listings_silver", "search_profiles", "recommendation_runs"]:
        r = q(f"select count(*) from {tbl}")
        if r: print(tbl, r.scalar())
    print("\n=== USERS ===")
    for tbl in ["users", "identities", "accounts"]:
        r = q(f"select count(*) from {tbl}")
        if r: print(tbl, r.scalar())
        else:
            # try list tables
            pass
    # list tables
    r = q("select tablename from pg_tables where schemaname='public' order by tablename")
    if r:
        print("\n=== TABLES ===")
        for row in r:
            print(row[0])
