import sys
sys.path.insert(0, "src")
import time, httpx
from sqlalchemy import create_engine, text

db_url = "postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway"
engine = create_engine(db_url, connect_args={"connect_timeout": 15})

# Fake centroids for fallback
FAKE = {
    "palermo": (-34.5851, -58.4246),
    "palermo hollywood": (-34.5800, -58.4360),
    "palermo soho": (-34.5880, -58.4280),
    "palermo chico": (-34.5810, -58.4050),
    "palermo nuevo": (-34.5750, -58.4150),
    "palermo viejo": (-34.5880, -58.4350),
    "las cañitas": (-34.5710, -58.4330),
    "las canitas": (-34.5710, -58.4330),
    "nunez": (-34.5540, -58.4620),
    "nuñez": (-34.5540, -58.4620),
    "barrio parque": (-34.5805, -58.4052),
    "botánico": (-34.5730, -58.4200),
    "botanico": (-34.5730, -58.4200),
}

def geocode(loc, nb):
    queries = []
    if loc and nb:
        queries.append(f"{loc}, {nb}, Buenos Aires, Argentina")
        queries.append(f"{loc}, Buenos Aires, Argentina")
    elif loc:
        queries.append(f"{loc}, Buenos Aires, Argentina")
    if nb:
        queries.append(f"{nb}, Buenos Aires, Argentina")
    # try each
    for q in queries:
        try:
            resp = httpx.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "ar"}, headers={"User-Agent": "Umbral/1.0 fix-all-geo"}, timeout=15)
            if resp.status_code == 200:
                js = resp.json()
                if js:
                    return float(js[0]['lat']), float(js[0]['lon']), q
        except Exception as e:
            print(f"httpx err {q}: {e}")
        time.sleep(1.1)
    # fallback fake
    key = (nb or "").strip().lower()
    if key in FAKE:
        lat, lon = FAKE[key]
        return lat, lon, f"FAKE:{key}"
    # try generic palermo
    if "palermo" in key:
        return FAKE["palermo"][0], FAKE["palermo"][1], "FAKE:palermo"
    return None, None, None

with engine.connect() as c:
    rows = c.execute(text("select id, location_text, neighborhood from silver_listings where geometry is null order by neighborhood, location_text")).fetchall()
    print(f"to fix: {len(rows)}")
    fixed = 0
    failed = 0
    for idx, (lid, loc, nb) in enumerate(rows):
        print(f"[{idx+1}/{len(rows)}] {lid} | {loc} | {nb}")
        lat, lon, used_q = geocode(loc, nb)
        if lat is not None:
            try:
                with engine.begin() as conn:
                    conn.execute(text("update silver_listings set geometry = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), geo_precision='block', geo_source=:src, updated_at=now() where id=:id"), {"lon": lon, "lat": lat, "src": "osm.nominatim" if not str(used_q).startswith("FAKE") else "fake.geocoder", "id": lid})
                print(f"  -> FIXED {lat},{lon} via {used_q}")
                fixed += 1
            except Exception as e:
                print(f"  -> DB ERR {e}")
                failed += 1
        else:
            print(f"  -> FAILED no geocode")
            failed += 1
        # small delay already inside geocode, but add extra for fake
        if used_q and used_q.startswith("FAKE"):
            time.sleep(0.2)
    print(f"DONE fixed={fixed} failed={failed}")
    # final counts
    for r in c.execute(text("select geo_precision, geo_source, count(*), count(geometry) from silver_listings group by 1,2 order by count(*) desc")):
        print(r)
