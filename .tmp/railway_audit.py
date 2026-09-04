import sys
sys.path.insert(0, "src")
from sqlalchemy import create_engine, text

db_url = "postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
engine = create_engine(db_url, connect_args={"connect_timeout": 10})

queries = [
    ("total silver_listings", "select count(*) from silver_listings"),
    ("by neighborhood+precision", "select neighborhood, geo_precision, count(*), count(geometry) from silver_listings group by neighborhood, geo_precision order by count(*) desc"),
    ("palermo count", "select count(*) from silver_listings where neighborhood ilike '%palermo%'"),
    ("palermo without geom", "select count(*) from silver_listings where neighborhood ilike '%palermo%' and geometry is null"),
    ("palermo sample", "select external_id, neighborhood, location_text, geo_precision, ST_AsText(geometry) as geom, price_value, rooms, surface_m2 from silver_listings where neighborhood ilike '%palermo%' limit 5"),
    ("nuñez sample", "select external_id, neighborhood, location_text, geo_precision, ST_AsText(geometry) as geom from silver_listings where neighborhood ilike '%nunez%' or neighborhood ilike '%nuñez%' limit 3"),
    ("import runs", "select state, count(*) from import_runs group by state"),
    ("raw snapshots", "select count(*) from raw_listing_snapshots"),
    ("tables", "select tablename from pg_tables where schemaname='public' order by tablename"),
]

with engine.connect() as c:
    for name, sql in queries:
        print(f"\n=== {name} ===")
        try:
            r = c.execute(text(sql))
            if "count" in name and "group" not in sql.lower() and "palermo" not in name.lower():
                print(r.scalar())
            else:
                rows = r.fetchall()
                for row in rows[:20]:
                    print(row)
                if len(rows) > 20:
                    print(f"... {len(rows)-20} more")
        except Exception as e:
            print(f"ERR: {e}")
