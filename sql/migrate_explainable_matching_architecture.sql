-- UMBRAL - Explainable matching architecture migration
-- Future-state migration: no backwards compatibility with raw_listing feedback/notifications.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS analyzed_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_listing_id UUID NOT NULL REFERENCES raw_listings(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    currency_original TEXT NOT NULL,
    price_original NUMERIC NOT NULL,
    price_usd NUMERIC NOT NULL,
    price_per_m2_usd NUMERIC DEFAULT 0,
    neighborhood TEXT NOT NULL,
    rooms INTEGER NOT NULL,
    scores JSONB NOT NULL,
    features JSONB NOT NULL,
    style_tags TEXT[] DEFAULT '{}',
    executive_summary TEXT NOT NULL,
    quality_score INTEGER DEFAULT 70 CHECK (quality_score >= 0 AND quality_score <= 100),
    quality_reasons JSONB DEFAULT '[]',
    property_signal_score INTEGER DEFAULT 70 CHECK (property_signal_score >= 0 AND property_signal_score <= 100),
    is_active BOOLEAN DEFAULT TRUE,
    embedding_vector vector(768),
    vibe_embedding vector(768),
    analysis_version TEXT DEFAULT '2.0',
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(raw_listing_id)
);

ALTER TABLE analyzed_listings
ADD COLUMN IF NOT EXISTS quality_score INTEGER DEFAULT 70 CHECK (quality_score >= 0 AND quality_score <= 100),
ADD COLUMN IF NOT EXISTS quality_reasons JSONB DEFAULT '[]',
ADD COLUMN IF NOT EXISTS property_signal_score INTEGER DEFAULT 70 CHECK (property_signal_score >= 0 AND property_signal_score <= 100),
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_analyzed_listings_neighborhood ON analyzed_listings(neighborhood);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_rooms ON analyzed_listings(rooms);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_price_usd ON analyzed_listings(price_usd);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_quality_score ON analyzed_listings(quality_score);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_is_active ON analyzed_listings(is_active);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_analyzed_at ON analyzed_listings(analyzed_at DESC);

CREATE INDEX IF NOT EXISTS idx_analyzed_listings_embedding
ON analyzed_listings USING hnsw (embedding_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_analyzed_listings_vibe_embedding
ON analyzed_listings USING hnsw (vibe_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

DROP TABLE IF EXISTS user_listing_matches CASCADE;
CREATE TABLE user_listing_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analyzed_listing_id UUID NOT NULL REFERENCES analyzed_listings(id) ON DELETE CASCADE,
    final_score INTEGER NOT NULL CHECK (final_score >= 0 AND final_score <= 100),
    band TEXT NOT NULL CHECK (band IN ('excellent', 'strong', 'possible', 'weak', 'poor', 'ineligible')),
    summary TEXT NOT NULL,
    criteria_breakdown JSONB NOT NULL DEFAULT '[]',
    gaps JSONB NOT NULL DEFAULT '[]',
    scoring_version TEXT NOT NULL DEFAULT '1.0',
    preference_version TEXT NOT NULL DEFAULT '1',
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    seen_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    liked_at TIMESTAMPTZ,
    notified_at TIMESTAMPTZ,
    UNIQUE(user_id, analyzed_listing_id)
);

CREATE INDEX idx_user_listing_matches_user_score ON user_listing_matches(user_id, final_score DESC);
CREATE INDEX idx_user_listing_matches_listing ON user_listing_matches(analyzed_listing_id);

DROP TABLE IF EXISTS ingestion_events CASCADE;
CREATE TABLE ingestion_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    external_id TEXT,
    url TEXT,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'rejected', 'error')),
    raw_listing_id UUID REFERENCES raw_listings(id) ON DELETE SET NULL,
    quality_score INTEGER DEFAULT 0 CHECK (quality_score >= 0 AND quality_score <= 100),
    reason TEXT,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ingestion_events_source_status ON ingestion_events(source, status);
CREATE INDEX idx_ingestion_events_created_at ON ingestion_events(created_at DESC);

DROP TABLE IF EXISTS personalized_match_explanations CASCADE;
CREATE TABLE personalized_match_explanations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analyzed_listing_id UUID NOT NULL REFERENCES analyzed_listings(id) ON DELETE CASCADE,
    explanation JSONB NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE(user_id, analyzed_listing_id)
);

-- Future-state contract: feedback and notifications are tied to analyzed listings.
CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analyzed_listing_id UUID REFERENCES analyzed_listings(id) ON DELETE CASCADE,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('like', 'dislike')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_feedback DROP CONSTRAINT IF EXISTS user_feedback_user_id_raw_listing_id_key;
ALTER TABLE user_feedback DROP COLUMN IF EXISTS raw_listing_id;
ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS analyzed_listing_id UUID REFERENCES analyzed_listings(id) ON DELETE CASCADE;
ALTER TABLE user_feedback ALTER COLUMN analyzed_listing_id SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_feedback_unique_analyzed
ON user_feedback(user_id, analyzed_listing_id);

CREATE TABLE IF NOT EXISTS sent_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analyzed_listing_id UUID REFERENCES analyzed_listings(id) ON DELETE CASCADE,
    final_score NUMERIC NOT NULL DEFAULT 0,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE sent_notifications DROP CONSTRAINT IF EXISTS sent_notifications_user_id_raw_listing_id_key;
ALTER TABLE sent_notifications DROP COLUMN IF EXISTS raw_listing_id;
ALTER TABLE sent_notifications ADD COLUMN IF NOT EXISTS analyzed_listing_id UUID REFERENCES analyzed_listings(id) ON DELETE CASCADE;
ALTER TABLE sent_notifications ALTER COLUMN analyzed_listing_id SET NOT NULL;
ALTER TABLE sent_notifications DROP COLUMN IF EXISTS similarity_score;
ALTER TABLE sent_notifications ADD COLUMN IF NOT EXISTS final_score NUMERIC NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS idx_sent_notifications_unique_analyzed
ON sent_notifications(user_id, analyzed_listing_id);

ALTER TABLE user_listing_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE personalized_match_explanations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access to user_listing_matches" ON user_listing_matches;
CREATE POLICY "Service role full access to user_listing_matches" ON user_listing_matches
    FOR ALL USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Service role full access to ingestion_events" ON ingestion_events;
CREATE POLICY "Service role full access to ingestion_events" ON ingestion_events
    FOR ALL USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Service role full access to personalized_match_explanations" ON personalized_match_explanations;
CREATE POLICY "Service role full access to personalized_match_explanations" ON personalized_match_explanations
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
