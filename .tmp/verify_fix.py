import sys
sys.path.insert(0,'src')
from sqlalchemy import create_engine, text
engine=create_engine('postgresql+psycopg://postgres:B0CB097E8DDFAFC938FE644072B12477@altaria.proxy.rlwy.net:13185/railway')
with engine.connect() as c:
    print('total', c.execute(text('select count(*) from silver_listings')).scalar())
    print('with geom', c.execute(text('select count(*) from silver_listings where geometry is not null')).scalar())
    print('by precision', list(c.execute(text('select geo_precision, count(*) from silver_listings group by geo_precision'))))
    for r in c.execute(text("select neighborhood, location_text, ST_AsText(geometry), geo_precision from silver_listings where neighborhood ilike '%palermo%' limit 3")):
        print(r)
    print('--- failing still ---')
    # check any still null
    print('null geom', c.execute(text('select count(*) from silver_listings where geometry is null')).scalar())
