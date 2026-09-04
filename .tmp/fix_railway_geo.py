import sys
sys.path.insert(0, "src")
import time, httpx
from sqlalchemy import create_engine, text

db_url = "postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
engine = create_engine(db_url, connect_args={"connect_timeout": 10})

# test update 3 first
test_ids = []
with engine.connect() as c:
    rows = c.execute(text("select id, location_text, neighborhood from silver_listings where geometry is null limit 3")).fetchall()
    for r in rows:
        print(r)
    # try geocode one and update
    for (lid, loc, nb) in rows:
        query = f"{loc}, {nb}, Ciudad Autonoma de Buenos Aires, Argentina" if loc and nb else (loc or nb or "")
        print(f"QUERY: {query}")
        try:
            resp = httpx.get("https://nominatim.openstreetmap.org/search", params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "ar"}, headers={"User-Agent": "Umbral/1.0 (fix-geo)"}, timeout=15)
            print("status", resp.status_code, resp.text[:500])
            js = resp.json()
            if js:
                print("result", js[0]['lat'], js[0]['lon'], js[0]['display_name'][:100])
                # do update
                lat = float(js[0]['lat'])
                lon = float(js[0]['lon'])
                # update in transaction
                with engine.begin() as conn:
                    conn.execute(text("update silver_listings set geometry = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), geo_precision='block', geo_source='osm.nominatim', updated_at=now() where id=:id"), {"lon": lon, "lat": lat, "id": lid})
                print(f"updated {lid}")
            else:
                print("no result")
        except Exception as e:
            print(f"err {e}")
        time.sleep(1.2)
    # verify
    for r in c.execute(text("select id, neighborhood, location_text, geo_precision, geo_source, ST_AsText(geometry) from silver_listings where id in (select id from silver_listings where geometry is not null and geo_source='osm.nominatim' limit 3)")):
        print("verify", r)
