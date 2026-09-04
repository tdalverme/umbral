import sys
sys.path.insert(0,"src")
from sqlalchemy import create_engine, text
import httpx, time
engine=create_engine("postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway")
with engine.connect() as c:
    rows=c.execute(text("select id, location_text, neighborhood, ST_Y(geometry) as lat, ST_X(geometry) as lon from silver_listings where neighborhood ilike '%caballito%'")).fetchall()
    outliers=[]
    for r in rows:
        lid,loc,nb,lat,lon=r
        if not (-34.70 <= lat <= -34.52 and -58.55 <= lon <= -58.32):
            outliers.append(r)
            print(f"OUTLIER {loc}|{nb}|{lat},{lon}")
    print(f"outliers {len(outliers)}")
    for lid,loc,nb,lat,lon in outliers:
        # try with explicit CABA and bounded viewbox
        for q in [f"{loc}, {nb}, Ciudad Autonoma de Buenos Aires, Argentina", f"{loc}, Caballito, CABA, Argentina"]:
            try:
                resp=httpx.get("https://nominatim.openstreetmap.org/search", params={"q":q,"format":"jsonv2","limit":1,"countrycodes":"ar","viewbox":"-58.55,-34.52,-58.32,-34.70","bounded":1}, headers={"User-Agent":"Umbral outlier2"}, timeout=15)
                js=resp.json()
                if js:
                    nlat=float(js[0]['lat']); nlon=float(js[0]['lon'])
                    if -34.70 <= nlat <= -34.52 and -58.55 <= nlon <= -58.32:
                        print(f"  FIX {q} -> {nlat},{nlon}")
                        with engine.begin() as conn:
                            conn.execute(text("update silver_listings set geometry=ST_SetSRID(ST_MakePoint(:lon,:lat),4326), updated_at=now() where id=:id"), {"lon":nlon,"lat":nlat,"id":lid})
                        break
                    else:
                        print(f"  still outlier {q} -> {nlat},{nlon}")
                else:
                    print(f"  no result {q}")
            except Exception as e:
                print(e)
            time.sleep(1.1)
        else:
            # fallback to caballito centroid
            with engine.begin() as conn:
                conn.execute(text("update silver_listings set geometry=ST_SetSRID(ST_MakePoint(-58.4442,-34.6204),4326), geo_source='fake.geocoder', updated_at=now() where id=:id"), {"id":lid})
            print(f"  FAKE fallback {loc}")
        time.sleep(0.5)
    # verify
    with engine.connect() as c2:
        rows2=c2.execute(text("select location_text, neighborhood, ST_Y(geometry), ST_X(geometry) from silver_listings where neighborhood ilike '%caballito%'")).fetchall()
        bad=[r for r in rows2 if not (-34.70 <= r[2] <= -34.52 and -58.55 <= r[3] <= -58.32)]
        print(f"still bad {len(bad)}")
        for r in bad:
            print(r)
