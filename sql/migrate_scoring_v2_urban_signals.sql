-- UMBRAL - Scoring v2: normalized listing data + cached urban signals

CREATE EXTENSION IF NOT EXISTS postgis;

ALTER TABLE analyzed_listings
ADD COLUMN IF NOT EXISTS maintenance_fee_usd NUMERIC NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_monthly_cost_usd NUMERIC NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS size_total_m2 NUMERIC NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS size_covered_m2 NUMERIC NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS location_geom geography(Point, 4326);

UPDATE analyzed_listings
SET total_monthly_cost_usd = price_usd
WHERE total_monthly_cost_usd = 0;

UPDATE analyzed_listings
SET location_geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
WHERE location_geom IS NULL
  AND latitude IS NOT NULL
  AND longitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_analyzed_listings_location_geom
ON analyzed_listings USING GIST(location_geom);

CREATE INDEX IF NOT EXISTS idx_analyzed_listings_total_monthly_cost
ON analyzed_listings(total_monthly_cost_usd);

CREATE INDEX IF NOT EXISTS idx_analyzed_listings_size_covered_m2
ON analyzed_listings(size_covered_m2);

CREATE TABLE IF NOT EXISTS osm_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_path TEXT NOT NULL,
    source_hash TEXT,
    status TEXT NOT NULL DEFAULT 'importing' CHECK (status IN ('importing', 'ready', 'failed')),
    poi_count INTEGER NOT NULL DEFAULT 0,
    linear_count INTEGER NOT NULL DEFAULT 0,
    imported_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_osm_snapshots_status_imported
ON osm_snapshots(status, imported_at DESC);

CREATE TABLE IF NOT EXISTS osm_pois (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    osm_snapshot_id UUID NOT NULL REFERENCES osm_snapshots(id) ON DELETE CASCADE,
    osm_id TEXT NOT NULL,
    category TEXT NOT NULL,
    name TEXT,
    tags JSONB NOT NULL DEFAULT '{}',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    geom geography(Point, 4326) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(osm_snapshot_id, osm_id, category)
);

CREATE INDEX IF NOT EXISTS idx_osm_pois_snapshot_category
ON osm_pois(osm_snapshot_id, category);

CREATE INDEX IF NOT EXISTS idx_osm_pois_tags
ON osm_pois USING GIN(tags);

CREATE INDEX IF NOT EXISTS idx_osm_pois_geom
ON osm_pois USING GIST(geom);

CREATE TABLE IF NOT EXISTS osm_linear_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    osm_snapshot_id UUID NOT NULL REFERENCES osm_snapshots(id) ON DELETE CASCADE,
    osm_id TEXT NOT NULL,
    category TEXT NOT NULL,
    name TEXT,
    tags JSONB NOT NULL DEFAULT '{}',
    geom geography(LineString, 4326) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(osm_snapshot_id, osm_id, category)
);

CREATE INDEX IF NOT EXISTS idx_osm_linear_snapshot_category
ON osm_linear_features(osm_snapshot_id, category);

CREATE INDEX IF NOT EXISTS idx_osm_linear_tags
ON osm_linear_features USING GIN(tags);

CREATE INDEX IF NOT EXISTS idx_osm_linear_geom
ON osm_linear_features USING GIST(geom);

CREATE TABLE IF NOT EXISTS listing_urban_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analyzed_listing_id UUID NOT NULL REFERENCES analyzed_listings(id) ON DELETE CASCADE,
    osm_snapshot_id UUID REFERENCES osm_snapshots(id) ON DELETE SET NULL,
    signals JSONB NOT NULL,
    computed_version TEXT NOT NULL DEFAULT 'urban_signals_v1',
    confidence NUMERIC NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(analyzed_listing_id, computed_version)
);

CREATE INDEX IF NOT EXISTS idx_listing_urban_signals_listing
ON listing_urban_signals(analyzed_listing_id);

CREATE INDEX IF NOT EXISTS idx_listing_urban_signals_confidence
ON listing_urban_signals(confidence);

CREATE INDEX IF NOT EXISTS idx_listing_urban_signals_json
ON listing_urban_signals USING GIN(signals);

CREATE TABLE IF NOT EXISTS market_price_benchmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_type TEXT NOT NULL CHECK (operation_type IN ('alquiler', 'venta')),
    neighborhood TEXT NOT NULL,
    rooms INTEGER NOT NULL,
    median_price_per_m2_usd NUMERIC NOT NULL,
    p25_price_per_m2_usd NUMERIC,
    p75_price_per_m2_usd NUMERIC,
    sample_count INTEGER NOT NULL DEFAULT 0,
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(operation_type, neighborhood, rooms)
);

CREATE INDEX IF NOT EXISTS idx_market_price_benchmarks_lookup
ON market_price_benchmarks(operation_type, neighborhood, rooms);

CREATE OR REPLACE FUNCTION get_urban_distance_buckets(
    p_latitude DOUBLE PRECISION,
    p_longitude DOUBLE PRECISION,
    p_snapshot_id UUID,
    p_radius_m INTEGER DEFAULT 1200
)
RETURNS TABLE (
    feature_kind TEXT,
    category TEXT,
    distance_m DOUBLE PRECISION
)
LANGUAGE sql
STABLE
AS $$
    WITH origin AS (
        SELECT ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326)::geography AS geom
    )
    SELECT
        'poi'::TEXT AS feature_kind,
        poi.category,
        ST_Distance(poi.geom, origin.geom) AS distance_m
    FROM osm_pois poi, origin
    WHERE poi.osm_snapshot_id = p_snapshot_id
      AND ST_DWithin(poi.geom, origin.geom, p_radius_m)

    UNION ALL

    SELECT
        'linear'::TEXT AS feature_kind,
        lf.category,
        ST_Distance(lf.geom, origin.geom) AS distance_m
    FROM osm_linear_features lf, origin
    WHERE lf.osm_snapshot_id = p_snapshot_id
      AND ST_DWithin(lf.geom, origin.geom, p_radius_m);
$$;

CREATE OR REPLACE FUNCTION refresh_market_price_benchmarks()
RETURNS VOID
LANGUAGE sql
AS $$
    INSERT INTO market_price_benchmarks (
        operation_type,
        neighborhood,
        rooms,
        median_price_per_m2_usd,
        p25_price_per_m2_usd,
        p75_price_per_m2_usd,
        sample_count,
        computed_at
    )
    SELECT
        rl.operation_type,
        al.neighborhood,
        al.rooms,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY al.price_per_m2_usd),
        percentile_cont(0.25) WITHIN GROUP (ORDER BY al.price_per_m2_usd),
        percentile_cont(0.75) WITHIN GROUP (ORDER BY al.price_per_m2_usd),
        COUNT(*),
        NOW()
    FROM analyzed_listings al
    JOIN raw_listings rl ON rl.id = al.raw_listing_id
    WHERE al.price_per_m2_usd > 0
      AND al.is_active = TRUE
    GROUP BY rl.operation_type, al.neighborhood, al.rooms
    ON CONFLICT (operation_type, neighborhood, rooms)
    DO UPDATE SET
        median_price_per_m2_usd = EXCLUDED.median_price_per_m2_usd,
        p25_price_per_m2_usd = EXCLUDED.p25_price_per_m2_usd,
        p75_price_per_m2_usd = EXCLUDED.p75_price_per_m2_usd,
        sample_count = EXCLUDED.sample_count,
        computed_at = NOW();
$$;

ALTER TABLE osm_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE osm_pois ENABLE ROW LEVEL SECURITY;
ALTER TABLE osm_linear_features ENABLE ROW LEVEL SECURITY;
ALTER TABLE listing_urban_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_price_benchmarks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access to osm_snapshots" ON osm_snapshots
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access to osm_pois" ON osm_pois
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access to osm_linear_features" ON osm_linear_features
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access to listing_urban_signals" ON listing_urban_signals
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access to market_price_benchmarks" ON market_price_benchmarks
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
