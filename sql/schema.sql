-- =====================================================
-- UMBRAL - Schema de Base de Datos
-- Sistema de Recomendación Inmobiliaria Proactiva
-- =====================================================
-- Ejecutar este script en el SQL Editor de Supabase
-- https://app.supabase.com/project/YOUR_PROJECT/sql

-- Habilitar extensión pgvector para búsqueda semántica
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- CAPA BRONZE: raw_listings
-- Datos crudos sin transformación
-- =====================================================

CREATE TABLE IF NOT EXISTS raw_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identificación
    external_id TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('mercadolibre', 'zonaprop', 'argenprop')),
    hash_id TEXT NOT NULL,
    
    -- Contenido
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    
    -- Precio
    price TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency IN ('USD', 'ARS')),
    
    -- Ubicación
    location TEXT NOT NULL,
    region TEXT DEFAULT 'CABA',
    city TEXT DEFAULT 'Buenos Aires',
    neighborhood TEXT NOT NULL,
    
    -- Características físicas
    rooms TEXT NOT NULL,
    bathrooms TEXT DEFAULT '1',
    size_total TEXT DEFAULT '',
    size_covered TEXT DEFAULT '',
    
    -- Opcionales
    age TEXT,
    disposition TEXT,
    orientation TEXT,
    maintenance_fee TEXT,
    operation_type TEXT DEFAULT 'alquiler' CHECK (operation_type IN ('alquiler', 'venta')),
    
    -- Media y extras
    images TEXT[] DEFAULT '{}',
    coordinates JSONB,
    parking_spaces INTEGER,
    features JSONB NOT NULL DEFAULT '{}',
    
    -- Metadatos
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(source, external_id),
    UNIQUE(hash_id)
);

-- Índices para raw_listings
CREATE INDEX IF NOT EXISTS idx_raw_listings_source ON raw_listings(source);
CREATE INDEX IF NOT EXISTS idx_raw_listings_neighborhood ON raw_listings(neighborhood);
CREATE INDEX IF NOT EXISTS idx_raw_listings_hash ON raw_listings(hash_id);
CREATE INDEX IF NOT EXISTS idx_raw_listings_scraped_at ON raw_listings(scraped_at DESC);

-- Índice GIN para búsqueda en features (JSONB)
CREATE INDEX IF NOT EXISTS idx_raw_listings_features ON raw_listings USING GIN(features);


-- =====================================================
-- CAPA GOLD: analyzed_listings
-- Datos procesados y enriquecidos por IA
-- =====================================================

CREATE TABLE IF NOT EXISTS analyzed_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Referencias
    raw_listing_id UUID NOT NULL REFERENCES raw_listings(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    
    -- Datos económicos normalizados
    currency_original TEXT NOT NULL,
    price_original NUMERIC NOT NULL,
    price_usd NUMERIC NOT NULL,
    price_per_m2_usd NUMERIC DEFAULT 0,
    
    -- Datos geográficos
    neighborhood TEXT NOT NULL,
    rooms INTEGER NOT NULL,
    
    -- Inteligencia extraída (JSONB)
    scores JSONB NOT NULL,
    features JSONB NOT NULL,
    style_tags TEXT[] DEFAULT '{}',
    executive_summary TEXT NOT NULL,
    
    -- Vector para búsqueda semántica (768 dimensiones para text-embedding-004)
    embedding_vector vector(768),
    
    -- Vibe embedding: solo executive_summary + style_tags para matching cualitativo
    vibe_embedding vector(768),
    
    -- Control de versión
    analysis_version TEXT DEFAULT '2.0',
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(raw_listing_id)
);

-- Índices para analyzed_listings
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_neighborhood ON analyzed_listings(neighborhood);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_rooms ON analyzed_listings(rooms);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_price_usd ON analyzed_listings(price_usd);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_analyzed_at ON analyzed_listings(analyzed_at DESC);

-- Índice GIN para scores y features
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_scores ON analyzed_listings USING GIN(scores);
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_features ON analyzed_listings USING GIN(features);

-- Índice HNSW para búsqueda vectorial eficiente
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_embedding 
ON analyzed_listings USING hnsw (embedding_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Índice HNSW para vibe embedding (matching cualitativo)
CREATE INDEX IF NOT EXISTS idx_analyzed_listings_vibe_embedding 
ON analyzed_listings USING hnsw (vibe_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);


-- =====================================================
-- USUARIOS
-- =====================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Telegram
    telegram_id BIGINT UNIQUE NOT NULL,
    telegram_username TEXT,
    
    -- Preferencias (JSONB para flexibilidad)
    preferences JSONB NOT NULL DEFAULT '{
        "hard_filters": {
            "min_price_usd": null,
            "max_price_usd": null,
            "neighborhoods": [],
            "min_rooms": null,
            "max_rooms": null,
            "min_size_m2": null,
            "operation_type": "alquiler",
            "requires_balcony": false,
            "requires_parking": false,
            "requires_pets_allowed": false,
            "requires_furnished": false
        },
        "soft_preferences": {
            "weight_quietness": 0.5,
            "weight_luminosity": 0.5,
            "weight_connectivity": 0.5,
            "weight_wfh_suitability": 0.5,
            "weight_modernity": 0.5,
            "weight_green_spaces": 0.5,
            "ideal_description": null
        }
    }',
    
    -- Vector de preferencia para matching semántico
    preference_vector vector(768),
    
    -- Estado
    is_active BOOLEAN DEFAULT TRUE,
    onboarding_completed BOOLEAN DEFAULT FALSE,
    onboarding_step INTEGER DEFAULT 0,
    
    -- Estadísticas
    total_likes INTEGER DEFAULT 0,
    total_dislikes INTEGER DEFAULT 0,
    
    -- Metadatos
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para users
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_onboarding ON users(onboarding_completed);


-- =====================================================
-- FEEDBACK DE USUARIOS
-- =====================================================

CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analyzed_listing_id UUID NOT NULL REFERENCES analyzed_listings(id) ON DELETE CASCADE,
    
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('like', 'dislike')),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Un usuario solo puede dar feedback una vez por listing
    UNIQUE(user_id, analyzed_listing_id)
);

-- Índices para user_feedback
CREATE INDEX IF NOT EXISTS idx_user_feedback_user ON user_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_listing ON user_feedback(analyzed_listing_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_type ON user_feedback(feedback_type);


-- =====================================================
-- NOTIFICACIONES ENVIADAS
-- Para evitar spam y trackear qué se envió a quién
-- =====================================================

CREATE TABLE IF NOT EXISTS sent_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analyzed_listing_id UUID NOT NULL REFERENCES analyzed_listings(id) ON DELETE CASCADE,
    
    similarity_score NUMERIC NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- No enviar el mismo listing dos veces al mismo usuario
    UNIQUE(user_id, analyzed_listing_id)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_sent_notifications_user ON sent_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_sent_notifications_sent_at ON sent_notifications(sent_at DESC);


-- =====================================================
-- FUNCIONES ÚTILES
-- =====================================================

-- Función para buscar listings similares usando similitud de coseno
CREATE OR REPLACE FUNCTION search_similar_listings(
    query_embedding vector(768),
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
AS $$
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
$$;


-- Función para obtener listings que matchean los hard filters de un usuario
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
    embedding_vector vector(768)
)
LANGUAGE plpgsql
AS $$
DECLARE
    user_prefs JSONB;
    hard_filters JSONB;
BEGIN
    -- Obtener preferencias del usuario
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
        -- Filtro de precio mínimo
        (hard_filters->>'min_price_usd' IS NULL 
         OR al.price_usd >= (hard_filters->>'min_price_usd')::NUMERIC)
        -- Filtro de precio máximo
        AND (hard_filters->>'max_price_usd' IS NULL 
             OR al.price_usd <= (hard_filters->>'max_price_usd')::NUMERIC)
        -- Filtro de barrios
        AND (hard_filters->'neighborhoods' = '[]'::JSONB 
             OR al.neighborhood = ANY(SELECT jsonb_array_elements_text(hard_filters->'neighborhoods')))
        -- Filtro de ambientes mínimos
        AND (hard_filters->>'min_rooms' IS NULL 
             OR al.rooms >= (hard_filters->>'min_rooms')::INTEGER)
        -- Filtro de ambientes máximos
        AND (hard_filters->>'max_rooms' IS NULL 
             OR al.rooms <= (hard_filters->>'max_rooms')::INTEGER)
        -- Filtro de tipo de operación
        AND (hard_filters->>'operation_type' IS NULL 
             OR rl.operation_type = hard_filters->>'operation_type')
        -- Filtro de balcón requerido
        AND ((hard_filters->>'requires_balcony')::BOOLEAN = FALSE 
             OR (rl.features->>'has_balcony')::BOOLEAN = TRUE)
        -- Filtro de cochera requerida
        AND ((hard_filters->>'requires_parking')::BOOLEAN = FALSE 
             OR rl.parking_spaces > 0)
        -- Filtro de mascotas permitidas
        AND ((hard_filters->>'requires_pets_allowed')::BOOLEAN = FALSE 
             OR (rl.features->>'is_pet_friendly')::BOOLEAN = TRUE)
        -- Filtro de amoblado
        AND ((hard_filters->>'requires_furnished')::BOOLEAN = FALSE 
             OR (rl.features->>'is_furnished')::BOOLEAN = TRUE);
END;
$$;


-- Trigger para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- =====================================================
-- ROW LEVEL SECURITY (RLS)
-- Habilitar para producción
-- =====================================================

-- Por ahora deshabilitamos RLS para desarrollo
-- En producción, configurar políticas apropiadas

ALTER TABLE raw_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyzed_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE sent_notifications ENABLE ROW LEVEL SECURITY;

-- Políticas permisivas para service_role (desarrollo)
CREATE POLICY "Service role full access to raw_listings" ON raw_listings
    FOR ALL USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "Service role full access to analyzed_listings" ON analyzed_listings
    FOR ALL USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "Service role full access to users" ON users
    FOR ALL USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "Service role full access to user_feedback" ON user_feedback
    FOR ALL USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "Service role full access to sent_notifications" ON sent_notifications
    FOR ALL USING (TRUE) WITH CHECK (TRUE);


-- =====================================================
-- DATOS DE PRUEBA (opcional, comentar en producción)
-- =====================================================

-- Descomentar para insertar datos de prueba
/*
INSERT INTO users (telegram_id, telegram_username, onboarding_completed, preferences)
VALUES (
    123456789,
    'test_user',
    TRUE,
    '{
        "hard_filters": {
            "min_price_usd": 300,
            "max_price_usd": 800,
            "neighborhoods": ["Palermo", "Belgrano", "Nuñez"],
            "min_rooms": 2,
            "max_rooms": 3,
            "min_size_m2": 40,
            "operation_type": "alquiler",
            "requires_balcony": false,
            "requires_parking": false,
            "requires_pets_allowed": true,
            "requires_furnished": false
        },
        "soft_preferences": {
            "weight_quietness": 0.8,
            "weight_luminosity": 0.9,
            "weight_connectivity": 0.6,
            "weight_wfh_suitability": 0.9,
            "weight_modernity": 0.5,
            "weight_green_spaces": 0.7,
            "ideal_description": "Busco un departamento luminoso y silencioso, ideal para trabajar desde casa. Cerca de espacios verdes sería un plus."
        }
    }'
);
*/
