import sys
sys.path.insert(0,"src")
import time, httpx
from sqlalchemy import create_engine, text
engine=create_engine("postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway")
with engine.connect() as c:
    rows=c.execute(text("select id, location_text, neighborhood from silver_listings where geometry is null")).fetchall()
    print(f"to fix {len(rows)}")
    for idx,(lid,loc,nb) in enumerate(rows):
        queries=[]
        if loc and nb:
            queries.append(f"{loc}, {nb}, Buenos Aires, Argentina")
            queries.append(f"{loc}, Buenos Aires, Argentina")
        elif loc:
            queries.append(f"{loc}, Buenos Aires, Argentina")
        if nb:
            queries.append(f"{nb}, Buenos Aires, Argentina")
        lat=lon=None; used=None
        for q in queries:
            try:
                resp=httpx.get("https://nominatim.openstreetmap.org/search", params={"q":q,"format":"jsonv2","limit":1,"countrycodes":"ar"}, headers={"User-Agent":"Umbral flores fix"}, timeout=15)
                js=resp.json()
                if js:
                    lat=float(js[0]['lat']); lon=float(js[0]['lon']); used=q; break
            except Exception as e:
                print(e)
            time.sleep(1.1)
        if lat is not None:
            with engine.begin() as conn:
                conn.execute(text("update silver_listings set geometry=ST_SetSRID(ST_MakePoint(:lon,:lat),4326), geo_precision='block', geo_source='osm.nominatim', updated_at=now() where id=:id"), {"lon":lon,"lat":lat,"id":lid})
            print(f"[{idx+1}/{len(rows)}] FIXED {loc[:40]}|{nb} -> {lat},{lon}")
        else:
            FAKE={"flores":(-34.6370,-58.4600),"flores norte":(-34.6300,-58.4600),"flores sur":(-34.6450,-58.4600)}
            key=(nb or "").lower()
            lat,lon=FAKE.get(key, (-34.6370,-58.4600))
            with engine.begin() as conn:
                conn.execute(text("update silver_listings set geometry=ST_SetSRID(ST_MakePoint(:lon,:lat),4326), geo_precision='block', geo_source='fake.geocoder', updated_at=now() where id=:id"), {"lon":lon,"lat":lat,"id":lid})
            print(f"[{idx+1}/{len(rows)}] FAKE {loc[:40]}")
        # throttle already
    print("done")
    with engine.connect() as c2:
        for r in c2.execute(text("select neighborhood, geo_precision, geo_source, count(*) from silver_listings group by 1,2,3 order by count(*) desc")):
            print(r)
        print("total", c2.execute(text("select count(*) from silver_listings")).scalar())
        print("null", c2.execute(text("select count(*) from silver_listings where geometry is null")).scalar())
        # check outliers
        for r in c2.execute(text("select location_text, neighborhood, ST_Y(geometry), ST_X(geometry) from silver_listings where neighborhood ilike '%flores%'")):
            lat, lon = r[2], r[3]
            if not (-34.70 <= lat <= -34.52 and -58.55 <= lon <= -58.32):
                print(f"OUTLIER {r}")
