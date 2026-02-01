-- =====================================================
-- MIGRACIÓN: Agregar columna vibe_embedding
-- =====================================================
-- Este vector solo contiene el embedding del executive_summary + style_tags
-- para matching semántico más preciso contra la descripción del usuario.
--
-- El embedding_vector original contiene toda la info del listing (estructural + cualitativa)
-- El vibe_embedding solo contiene la parte cualitativa (el "vibe" de la propiedad)

-- Agregar la columna
ALTER TABLE analyzed_listings 
ADD COLUMN IF NOT EXISTS vibe_embedding vector(768);

-- Crear índice HNSW para búsqueda eficiente
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_vibe_embedding 
ON analyzed_listings USING hnsw (vibe_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Comentario descriptivo
COMMENT ON COLUMN analyzed_listings.vibe_embedding IS 
'Embedding del executive_summary + style_tags para matching de "vibe" con preferencias del usuario';

-- Función actualizada para búsqueda por vibe
CREATE OR REPLACE FUNCTION search_listings_by_vibe(
    query_embedding vector(768),
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
AS $$
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
$$;
