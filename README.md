# 🏠 UMBRAL

**Sistema de Recomendación Inmobiliaria Proactiva**

Transforma la búsqueda de vivienda de un proceso pasivo a uno proactivo. El sistema extrae el "valor invisible" de los anuncios (luz, silencio, vibra) mediante IA y notifica al usuario solo cuando el match es excepcional.

## ✨ Características

- 🔍 **Scraping inteligente** de MercadoLibre Inmuebles (CABA)
- 🤖 **Análisis con IA** usando Gemini 1.5 Flash para extraer:
  - Scores cualitativos (silencio, luminosidad, conectividad)
  - Características inferidas (vibe del barrio, tipo de vista)
  - Resumen ejecutivo honesto
- 🎯 **Matching personalizado** combinando filtros hard y similitud semántica
- 📱 **Bot de Telegram** para onboarding y notificaciones
- 🔄 **Automatización** con GitHub Actions (cron cada hora)

## 🏗️ Arquitectura

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Playwright    │────▶│   Supabase   │◀────│   Gemini AI     │
│   (Scraping)    │     │  PostgreSQL  │     │   (Análisis)    │
└─────────────────┘     │  + pgvector  │     └─────────────────┘
                        └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │   Matching   │
                        │    Engine    │
                        └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │   Telegram   │
                        │     Bot      │
                        └──────────────┘
```

### Arquitectura de Datos (Medallion)

- **Bronze (raw_listings)**: Datos crudos sin transformar
- **Gold (analyzed_listings)**: Datos procesados con scores y embeddings

## 🚀 Setup

### 1. Requisitos

- Python 3.11+
- Cuenta de [Supabase](https://supabase.com) (free tier)
- API Key de [Google Gemini](https://makersuite.google.com/app/apikey)
- Bot de Telegram (crear con [@BotFather](https://t.me/botfather))

### 2. Instalación

```bash
# Clonar repositorio
git clone https://github.com/tu-usuario/umbral.git
cd umbral

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o: .\venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Instalar Playwright
playwright install chromium
```

### 3. Configuración de Supabase

1. Crear proyecto en [Supabase](https://app.supabase.com)
2. Ir a **SQL Editor** y ejecutar el contenido de `sql/schema.sql`
3. Copiar las credenciales de **Settings > API**:
   - Project URL → `SUPABASE_URL`
   - anon public → `SUPABASE_KEY`
   - service_role → `SUPABASE_SERVICE_KEY`

### 4. Configuración del Bot de Telegram

1. Abrir [@BotFather](https://t.me/botfather) en Telegram
2. Enviar `/newbot` y seguir instrucciones
3. Copiar el token → `TELEGRAM_BOT_TOKEN`

### 5. Variables de Entorno

Copiar `env.example` a `.env` y completar:

```bash
cp env.example .env
```

```env
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbG...
SUPABASE_SERVICE_KEY=eyJhbG...

# Gemini
GEMINI_API_KEY=AIza...

# Telegram
TELEGRAM_BOT_TOKEN=7123456789:AAF...

# Opcional
SIMILARITY_THRESHOLD=0.85
ARS_TO_USD_RATE=1000
```

## 📖 Uso

### Ejecutar el Bot (desarrollo)

```bash
cd src
python -m umbral.scripts.run_bot
```

El bot estará disponible en Telegram. Los usuarios pueden:
1. Iniciar con `/start`
2. Completar el onboarding (tipo, barrios, presupuesto, preferencias)
3. Recibir notificaciones de propiedades que matchean

### Ejecutar Scraping Manual

```bash
cd src

# Scrapear alquileres en CABA
python -m umbral.scripts.run_scraper --operation alquiler

# Scrapear barrios específicos
python -m umbral.scripts.run_scraper --neighborhoods Palermo,Belgrano,Nuñez

# Scrapear más páginas
python -m umbral.scripts.run_scraper --max-pages 10
```

### Ejecutar Análisis Manual

```bash
cd src
python -m umbral.scripts.run_analysis --limit 50
```

### Ejecutar Matching Manual

```bash
cd src
python -m umbral.scripts.run_matching
```

## ⚙️ GitHub Actions

El sistema incluye un workflow que se ejecuta cada hora:

1. **Scrape**: Extrae nuevas propiedades de MercadoLibre
2. **Analyze**: Procesa con Gemini y genera embeddings
3. **Match**: Busca matches y envía notificaciones

### Configurar Secrets en GitHub

Ir a **Settings > Secrets and variables > Actions** y agregar:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_KEY`
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`

### Ejecutar Manualmente

Ir a **Actions > Scrape & Analyze Properties > Run workflow**

## 📊 Modelo de Datos

### RawListing (Bronze)

```python
class RawListing:
    external_id: str      # ID del portal
    url: str              # URL del anuncio
    source: str           # mercadolibre, zonaprop, argenprop
    title: str
    description: str
    price: str
    currency: str         # USD o ARS
    neighborhood: str
    rooms: str
    features: dict        # is_furnished, has_balcony, etc.
    hash_id: str          # Para detectar cambios
```

### AnalyzedListing (Gold)

```python
class AnalyzedListing:
    raw_listing_id: str
    price_usd: float      # Precio normalizado
    price_per_m2_usd: float
    
    scores: PropertyScores  # quietness, luminosity, etc.
    features: InferredFeatures  # neighborhood_vibe, view_type
    style_tags: list[str]   # ["luminoso", "moderno"]
    executive_summary: str  # Resumen de 280 chars
    
    embedding_vector: list[float]  # 768 dimensiones
```

### User

```python
class User:
    telegram_id: int
    preferences: UserPreferences
    preference_vector: list[float]  # Para matching semántico
    is_active: bool
    onboarding_completed: bool
```

## 🔮 Roadmap

- [ ] Agregar scraper de ZonaProp
- [ ] Agregar scraper de ArgenProp
- [ ] Búsqueda por texto libre ("algo luminoso en Palermo")
- [ ] Historial de propiedades vistas
- [ ] Alertas de cambio de precio
- [ ] Soporte para GBA

## 🤝 Contribuir

1. Fork el repositorio
2. Crear branch (`git checkout -b feature/nueva-feature`)
3. Commit cambios (`git commit -am 'Agrega nueva feature'`)
4. Push al branch (`git push origin feature/nueva-feature`)
5. Crear Pull Request

## 📄 Licencia

MIT License - ver [LICENSE](LICENSE) para detalles.

---

Desarrollado con ❤️ en Buenos Aires 🇦🇷
