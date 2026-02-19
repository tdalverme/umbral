-- =====================================================
-- UMBRAL - Migracion a flujo RAW-only (sin analyzed_listings)
-- =====================================================
-- Objetivo:
-- 1) Guardar embeddings en raw_listings
-- 2) Mover feedback/notificaciones a raw_listing_id
-- 3) Eliminar dependencia de analyzed_listings

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- 1) Embedding directo en raw_listings
ALTER TABLE raw_listings
ADD COLUMN IF NOT EXISTS embedding_vector vector(768);

CREATE INDEX IF NOT EXISTS idx_raw_listings_embedding
ON raw_listings USING hnsw (embedding_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 2) user_feedback -> raw_listing_id
ALTER TABLE user_feedback
ADD COLUMN IF NOT EXISTS raw_listing_id UUID;

-- Backfill desde analyzed_listings cuando exista y haya FK anterior
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'user_feedback' AND column_name = 'analyzed_listing_id'
    ) THEN
        UPDATE user_feedback uf
        SET raw_listing_id = al.raw_listing_id
        FROM analyzed_listings al
        WHERE uf.analyzed_listing_id = al.id
          AND uf.raw_listing_id IS NULL;
    END IF;
END $$;

ALTER TABLE user_feedback
ALTER COLUMN raw_listing_id SET NOT NULL;

ALTER TABLE user_feedback
DROP CONSTRAINT IF EXISTS user_feedback_analyzed_listing_id_fkey;

ALTER TABLE user_feedback
ADD CONSTRAINT user_feedback_raw_listing_id_fkey
FOREIGN KEY (raw_listing_id) REFERENCES raw_listings(id) ON DELETE CASCADE;

ALTER TABLE user_feedback
DROP CONSTRAINT IF EXISTS user_feedback_user_id_analyzed_listing_id_key;

ALTER TABLE user_feedback
ADD CONSTRAINT user_feedback_user_id_raw_listing_id_key UNIQUE (user_id, raw_listing_id);

DROP INDEX IF EXISTS idx_user_feedback_listing;
CREATE INDEX IF NOT EXISTS idx_user_feedback_listing ON user_feedback(raw_listing_id);

ALTER TABLE user_feedback DROP COLUMN IF EXISTS analyzed_listing_id;

-- 3) sent_notifications -> raw_listing_id
ALTER TABLE sent_notifications
ADD COLUMN IF NOT EXISTS raw_listing_id UUID;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'sent_notifications' AND column_name = 'analyzed_listing_id'
    ) THEN
        UPDATE sent_notifications sn
        SET raw_listing_id = al.raw_listing_id
        FROM analyzed_listings al
        WHERE sn.analyzed_listing_id = al.id
          AND sn.raw_listing_id IS NULL;
    END IF;
END $$;

ALTER TABLE sent_notifications
ALTER COLUMN raw_listing_id SET NOT NULL;

ALTER TABLE sent_notifications
DROP CONSTRAINT IF EXISTS sent_notifications_analyzed_listing_id_fkey;

ALTER TABLE sent_notifications
ADD CONSTRAINT sent_notifications_raw_listing_id_fkey
FOREIGN KEY (raw_listing_id) REFERENCES raw_listings(id) ON DELETE CASCADE;

ALTER TABLE sent_notifications
DROP CONSTRAINT IF EXISTS sent_notifications_user_id_analyzed_listing_id_key;

ALTER TABLE sent_notifications
ADD CONSTRAINT sent_notifications_user_id_raw_listing_id_key UNIQUE (user_id, raw_listing_id);

ALTER TABLE sent_notifications DROP COLUMN IF EXISTS analyzed_listing_id;

-- 4) Funciones viejas acopladas a analyzed_listings
DROP FUNCTION IF EXISTS search_similar_listings(vector, numeric, integer);
DROP FUNCTION IF EXISTS get_matching_listings_for_user(uuid);

-- 5) Eliminar capa analyzed si ya no se usa
DROP TABLE IF EXISTS analyzed_listings CASCADE;

COMMIT;
