import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
engine = create_engine('postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway', connect_args={'connect_timeout':10})
with engine.connect() as c:
    r = c.execute(text("select external_id, payload->>'latitude' as lat, payload->>'longitude' as lng, payload->>'address_text' as addr, payload->>'neighborhood' as nb from raw_listing_snapshots where payload->>'neighborhood' ilike '%palermo%' limit 5"))
    for row in r:
        print(row)
    print('--- geo_source ---')
    for row in c.execute(text("select geo_source, geo_precision, count(*) from silver_listings group by 1,2")):
        print(row)
    print('--- source_id ---')
    for row in c.execute(text("select source_id, count(*) from silver_listings group by source_id")):
        print(row)
    print('raw without lat', c.execute(text("select count(*) from raw_listing_snapshots where payload->>'latitude' is null")).scalar())
    print('raw with lat', c.execute(text("select count(*) from raw_listing_snapshots where payload->>'latitude' is not null")).scalar())
    print('import_runs')
    for row in c.execute(text("select batch_key, total_records, accepted, state, source_version from import_runs")):
        print(row)
    print('--- search_profiles ---')
    try:
        for row in c.execute(text("select id, name, status, zones from search_profiles limit 5")):
            print(row)
    except Exception as e:
        print(e)
    print('--- users ---')
    print("users", c.execute(text("select count(*) from product_users")).scalar())
    print("profiles", c.execute(text("select count(*) from search_profiles")).scalar())
