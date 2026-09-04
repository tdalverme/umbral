import sys
sys.path.insert(0, "src")
from sqlalchemy import create_engine, text
db_url = "postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
engine = create_engine(db_url, connect_args={"connect_timeout": 10})
with engine.connect() as c:
    print("=== import_runs detail ===")
    for row in c.execute(text("select run_id, source_id, batch_key, state, created_at, finished_at from import_runs order by created_at desc")):
        print(row)
    print("\n=== raw payload sample Palermo ===")
    # find a palermo snapshot and check payload has lat
    rows = c.execute(text("select external_id, payload->>'latitude' as lat, payload->>'longitude' as lng, payload->>'address_text' as addr, payload->>'neighborhood' as nb from raw_listing_snapshots where external_id like '%59397872%'"))
    for r in rows:
        print(r)
    rows = c.execute(text("select external_id, payload->>'latitude' as lat, payload->>'longitude' as lng from raw_listing_snapshots where payload->>'neighborhood' ilike '%palermo%' limit 3"))
    for r in rows:
        print(r)
    # check silver_listings geo_source
    print("\n=== silver geo_source ===")
    for r in c.execute(text("select neighborhood, geo_precision, geo_source, count(*) from silver_listings group by 1,2,3 order by count(*) desc limit 10")):
        print(r)
    # check canonical/dedupe
    print("\n=== canonical_properties ===")
    print(c.execute(text("select count(*) from canonical_properties")).scalar())
    print(c.execute(text("select count(*) from dedupe_links")).scalar(), "dedupe_links")
    # check recommendation runs
    print("\n=== search_profiles and rec runs ===")
    for r in c.execute(text("select id, name, status, zones from search_profiles limit 5")):
        print(r)
    try:
        for r in c.execute(text("select search_profile_id, state, count(*) from recommendation_runs group by 1,2 limit 10")):
            print(r)
    except Exception as e:
        print("rec runs err", e)
        for r in c.execute(text("select tablename from pg_tables where tablename like '%recommend%' or tablename like '%radar%'")):
            print(r)
    # check users
    try:
        print(c.execute(text("select count(*) from product_users")).scalar(), "product_users")
        print(c.execute(text("select count(*) from product_sessions")).scalar(), "sessions")
    except Exception as e:
        print(e)
