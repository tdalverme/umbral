-- =====================================================
-- UMBRAL - Migración de dimensiones (Matryoshka)
-- =====================================================
-- Objetivo:
--   Ajustar toda la capa vectorial a una dimensión objetivo para pgvector
--   (ejemplo típico: 768 -> 512) manteniendo compatibilidad de matching.
--
-- Uso:
--   1) Editar target_dim en el bloque DO (default 512).
--   2) Ejecutar en Supabase SQL Editor.
--   3) Actualizar .env:
--        EMBEDDING_OUTPUT_DIM=<target_dim>
--        EMBEDDING_STORAGE_DIM=<target_dim>
--
-- Nota:
--   - Esta migración trunca dimensiones al reducir tamaño (768 -> 512).
--   - Si se usa una dimensión mayor que la actual, el cast puede fallar
--     según la versión de pgvector y los datos existentes.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
DECLARE
    target_dim INTEGER := 512; -- Cambiar a 768 si querés mantener tamaño actual.
BEGIN
    IF target_dim <= 0 THEN
        RAISE EXCEPTION 'target_dim inválida: %', target_dim;
    END IF;

    -- -------------------------------------------------
    -- 1) Dropear índices vectoriales antes de ALTER TYPE
    -- -------------------------------------------------
    DROP INDEX IF EXISTS idx_analyzed_listings_embedding;
    DROP INDEX IF EXISTS idx_analyzed_listings_vibe_embedding;
    DROP INDEX IF EXISTS idx_raw_listings_embedding;

    -- -------------------------------------------------
    -- 2) Ajustar columnas vectoriales (si existen)
    -- -------------------------------------------------
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'analyzed_listings'
          AND column_name = 'embedding_vector'
    ) THEN
        EXECUTE format(
            'ALTER TABLE analyzed_listings
               ALTER COLUMN embedding_vector TYPE vector(%s)
               USING CASE
                   WHEN embedding_vector IS NULL THEN NULL
                   ELSE embedding_vector::vector(%s)
               END',
            target_dim, target_dim
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'analyzed_listings'
          AND column_name = 'vibe_embedding'
    ) THEN
        EXECUTE format(
            'ALTER TABLE analyzed_listings
               ALTER COLUMN vibe_embedding TYPE vector(%s)
               USING CASE
                   WHEN vibe_embedding IS NULL THEN NULL
                   ELSE vibe_embedding::vector(%s)
               END',
            target_dim, target_dim
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'raw_listings'
          AND column_name = 'embedding_vector'
    ) THEN
        EXECUTE format(
            'ALTER TABLE raw_listings
               ALTER COLUMN embedding_vector TYPE vector(%s)
               USING CASE
                   WHEN embedding_vector IS NULL THEN NULL
                   ELSE embedding_vector::vector(%s)
               END',
            target_dim, target_dim
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'preference_vector'
    ) THEN
        EXECUTE format(
            'ALTER TABLE users
               ALTER COLUMN preference_vector TYPE vector(%s)
               USING CASE
                   WHEN preference_vector IS NULL THEN NULL
                   ELSE preference_vector::vector(%s)
               END',
            target_dim, target_dim
        );
    END IF;

    -- -------------------------------------------------
    -- 3) Re-crear índices HNSW (si aplican)
    -- -------------------------------------------------
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'analyzed_listings'
          AND column_name = 'embedding_vector'
    ) THEN
        EXECUTE
            'CREATE INDEX IF NOT EXISTS idx_analyzed_listings_embedding
             ON analyzed_listings USING hnsw (embedding_vector vector_cosine_ops)
             WITH (m = 16, ef_construction = 64)';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'analyzed_listings'
          AND column_name = 'vibe_embedding'
    ) THEN
        EXECUTE
            'CREATE INDEX IF NOT EXISTS idx_analyzed_listings_vibe_embedding
             ON analyzed_listings USING hnsw (vibe_embedding vector_cosine_ops)
             WITH (m = 16, ef_construction = 64)';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'raw_listings'
          AND column_name = 'embedding_vector'
    ) THEN
        EXECUTE
            'CREATE INDEX IF NOT EXISTS idx_raw_listings_embedding
             ON raw_listings USING hnsw (embedding_vector vector_cosine_ops)
             WITH (m = 16, ef_construction = 64)';
    END IF;

    -- -------------------------------------------------
    -- 4) Re-crear funciones tipadas con vector(target_dim)
    -- -------------------------------------------------
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'analyzed_listings'
    ) THEN
        EXECUTE format(
            $fn$
            CREATE OR REPLACE FUNCTION search_similar_listings(
                query_embedding vector(%1$s),
                match_threshold FLOAT DEFAULT 0.85,
                match_count INT DEFAULT 10
            )
            RETURNS TABLE (
                id UUID,
                external_id TEXT,
                neighborhood TEXT,
                price_usd NUMERIC,
                executive_summary TEXT,
                similarity FLOAT
            )
            LANGUAGE plpgsql
            AS $body$
            BEGIN
                RETURN QUERY
                SELECT
                    al.id,
                    al.external_id,
                    al.neighborhood,
                    al.price_usd,
                    al.executive_summary,
                    1 - (al.embedding_vector <=> query_embedding) AS similarity
                FROM analyzed_listings al
                WHERE al.embedding_vector IS NOT NULL
                  AND 1 - (al.embedding_vector <=> query_embedding) > match_threshold
                ORDER BY al.embedding_vector <=> query_embedding
                LIMIT match_count;
            END;
            $body$;
            $fn$,
            target_dim
        );

        EXECUTE format(
            $fn$
            CREATE OR REPLACE FUNCTION get_matching_listings_for_user(
                p_user_id UUID
            )
            RETURNS TABLE (
                listing_id UUID,
                external_id TEXT,
                neighborhood TEXT,
                rooms INTEGER,
                price_usd NUMERIC,
                executive_summary TEXT,
                scores JSONB,
                embedding_vector vector(%1$s)
            )
            LANGUAGE plpgsql
            AS $body$
            DECLARE
                user_prefs JSONB;
                hard_filters JSONB;
            BEGIN
                SELECT preferences INTO user_prefs FROM users WHERE id = p_user_id;
                hard_filters := user_prefs->'hard_filters';

                RETURN QUERY
                SELECT
                    al.id AS listing_id,
                    al.external_id,
                    al.neighborhood,
                    al.rooms,
                    al.price_usd,
                    al.executive_summary,
                    al.scores,
                    al.embedding_vector
                FROM analyzed_listings al
                JOIN raw_listings rl ON al.raw_listing_id = rl.id
                WHERE
                    (hard_filters->>'min_price_usd' IS NULL
                     OR al.price_usd >= (hard_filters->>'min_price_usd')::NUMERIC)
                    AND (hard_filters->>'max_price_usd' IS NULL
                         OR al.price_usd <= (hard_filters->>'max_price_usd')::NUMERIC)
                    AND (hard_filters->'neighborhoods' = '[]'::JSONB
                         OR al.neighborhood = ANY(SELECT jsonb_array_elements_text(hard_filters->'neighborhoods')))
                    AND (hard_filters->>'min_rooms' IS NULL
                         OR al.rooms >= (hard_filters->>'min_rooms')::INTEGER)
                    AND (hard_filters->>'max_rooms' IS NULL
                         OR al.rooms <= (hard_filters->>'max_rooms')::INTEGER)
                    AND (hard_filters->>'operation_type' IS NULL
                         OR rl.operation_type = hard_filters->>'operation_type')
                    AND ((hard_filters->>'requires_balcony')::BOOLEAN = FALSE
                         OR (rl.features->>'has_balcony')::BOOLEAN = TRUE)
                    AND ((hard_filters->>'requires_parking')::BOOLEAN = FALSE
                         OR rl.parking_spaces > 0)
                    AND ((hard_filters->>'requires_pets_allowed')::BOOLEAN = FALSE
                         OR (rl.features->>'is_pet_friendly')::BOOLEAN = TRUE)
                    AND ((hard_filters->>'requires_furnished')::BOOLEAN = FALSE
                         OR (rl.features->>'is_furnished')::BOOLEAN = TRUE);
            END;
            $body$;
            $fn$,
            target_dim
        );

        EXECUTE format(
            $fn$
            CREATE OR REPLACE FUNCTION search_listings_by_vibe(
                query_embedding vector(%1$s),
                match_threshold FLOAT DEFAULT 0.7,
                match_count INT DEFAULT 20
            )
            RETURNS TABLE (
                id UUID,
                external_id TEXT,
                neighborhood TEXT,
                price_usd NUMERIC,
                executive_summary TEXT,
                style_tags TEXT[],
                vibe_similarity FLOAT
            )
            LANGUAGE plpgsql
            AS $body$
            BEGIN
                RETURN QUERY
                SELECT
                    al.id,
                    al.external_id,
                    al.neighborhood,
                    al.price_usd,
                    al.executive_summary,
                    al.style_tags,
                    1 - (al.vibe_embedding <=> query_embedding) AS vibe_similarity
                FROM analyzed_listings al
                WHERE al.vibe_embedding IS NOT NULL
                  AND 1 - (al.vibe_embedding <=> query_embedding) > match_threshold
                ORDER BY al.vibe_embedding <=> query_embedding
                LIMIT match_count;
            END;
            $body$;
            $fn$,
            target_dim
        );
    END IF;
END $$;

COMMIT;
