import sys
sys.path.insert(0,'src')
from sqlalchemy import create_engine, text
engine=create_engine('postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway')
with engine.connect() as c:
    for r in c.execute(text("select neighborhood, geo_precision, geo_source, count(*) from silver_listings where neighborhood ilike '%caballito%' group by 1,2,3")):
        print(r)
    print('--- sample cab ---')
    for r in c.execute(text("select location_text, neighborhood, geo_precision, geo_source, ST_AsText(geometry) from silver_listings where neighborhood ilike '%caballito%' limit 5")):
        print(r)
    print('--- total ---')
    print(c.execute(text("select count(*) from silver_listings")).scalar())
