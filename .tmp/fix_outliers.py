import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
import httpx, time

db_url = "postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
engine = create_engine(db_url)

# CABA bounds approx: lat -34.70 to -34.53, lon -58.53 to -58.35
with engine.connect() as c:
    rows = c.execute(text("select id, location_text, neighborhood, ST_Y(geometry) as lat, ST_X(geometry) as lon from silver_listings where geo_source='osm.nominatim'")).fetchall()
    outliers = []
    for r in rows:
        lid, loc, nb, lat, lon = r
        if lat is None or lon is None:
            continue
        # CABA approx
        if not (-34.70 <= lat <= -34.52 and -58.55 <= lon <= -58.32):
            outliers.append(r)
            print(f"OUTLIER {lid} {loc} | {nb} | {lat},{lon}")
    print(f"total outliers {len(outliers)}")
    # fix each outlier with better query
    for lid, loc, nb, lat, lon in outliers:
        # try with explicit CABA
        queries = [
            f"{loc}, {nb}, Ciudad Autonoma de Buenos Aires, Argentina",
            f"{loc}, Palermo, Ciudad Autonoma de Buenos Aires, Argentina",
            f"{loc}, Buenos Aires, Argentina",
        ]
        fixed = False
        for q in queries:
            try:
                resp = httpx.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "ar", "bounded": 1, "viewbox": "-58.55,-34.52,-58.32,-34.70"}, headers={"User-Agent": "Umbral outlier fix"}, timeout=15)
                js = resp.json()
                if js:
                    nlat = float(js[0]['lat'])
                    nlon = float(js[0]['lon'])
                    # check if within CABA now
                    if -34.70 <= nlat <= -34.52 and -58.55 <= nlon <= -58.32:
                        print(f"  FIX attempt {q} -> {nlat},{nlon} {js[0]['display_name'][:60]}")
                        with engine.begin() as conn:
                            conn.execute(text("update silver_listings set geometry = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), updated_at=now() where id=:id"), {"lon": nlon, "lat": nlat, "id": lid})
                        fixed = True
                        break
                    else:
                        print(f"  still outlier {q} -> {nlat},{nlon}")
            except Exception as e:
                print(f"  err {q}: {e}")
            time.sleep(1.1)
        if not fixed:
            # fallback to fake centroid
            FAKE = {
                "palermo": (-34.5851, -58.4246),
                "palermo chico": (-34.5810, -58.4050),
                "palermo hollywood": (-34.5820, -58.4360),
                "palermo soho": (-34.5880, -58.4280),
                "palermo nuevo": (-34.5750, -58.4150),
                "palermo viejo": (-34.5880, -58.4350),
            }
            key = (nb or "").lower().strip()
            fallback = FAKE.get(key, FAKE["palermo"])
            print(f"  FALLBACK FAKE {fallback} for {loc} | {nb}")
            with engine.begin() as conn:
                conn.execute(text("update silver_listings set geometry = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), geo_source='fake.geocoder', updated_at=now() where id=:id"), {"lon": fallback[1], "lat": fallback[0], "id": lid})
        time.sleep(0.5)
    # verify remaining
    with engine.connect() as c2:
        rows2 = c2.execute(text("select id, location_text, neighborhood, ST_Y(geometry) as lat, ST_X(geometry) as lon from silver_listings where geo_source in ('osm.nominatim','fake.geocoder')")).fetchall()
        still = [r for r in rows2 if not (-34.70 <= r[3] <= -34.52 and -58.55 <= r[4] <= -58.32)]
        print(f"still outliers after fix: {len(still)}")
        for r in still:
            print(r)
