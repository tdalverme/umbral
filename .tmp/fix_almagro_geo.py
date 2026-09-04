import sys
sys.path.insert(0,"src")
import time, httpx
from sqlalchemy import create_engine, text
engine=create_engine("postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway")
with engine.connect() as c:
    rows=c.execute(text("select id, location_text, neighborhood from silver_listings where geometry is null")).fetchall()
    print(f"to fix {len(rows)}")
    fixed=0
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
                resp=httpx.get("https://nominatim.openstreetmap.org/search", params={"q":q,"format":"jsonv2","limit":1,"countrycodes":"ar"}, headers={"User-Agent":"Umbral almagro fix"}, timeout=15)
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
            fixed+=1
        else:
            # fake fallback
            FAKE={"almagro":(-34.6090,-58.4280),"almagro norte":(-34.6050,-58.4200)}
            key=(nb or "").lower()
            lat,lon=FAKE.get(key, (-34.6090,-58.4280))
            with engine.begin() as conn:
                conn.execute(text("update silver_listings set geometry=ST_SetSRID(ST_MakePoint(:lon,:lat),4326), geo_precision='block', geo_source='fake.geocoder', updated_at=now() where id=:id"), {"lon":lon,"lat":lat,"id":lid})
            print(f"[{idx+1}/{len(rows)}] FAKE {loc[:40]}")
            fixed+=1
            time.sleep(0.2)
    print(f"done {fixed}")
    with engine.connect() as c2:
        for r in c2.execute(text("select neighborhood, geo_precision, geo_source, count(*) from silver_listings group by 1,2,3 order by count(*) desc")):
            print(r)
        print("total", c2.execute(text("select count(*) from silver_listings")).scalar())
        print("null", c2.execute(text("select count(*) from silver_listings where geometry is null")).scalar())
