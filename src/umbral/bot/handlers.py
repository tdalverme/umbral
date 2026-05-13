"""
Handlers para el bot de Telegram.

Implementa el flujo de onboarding y manejo de feedback.
"""

import json
import re
from typing import Optional

import structlog
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from umbral.config import CABA_NEIGHBORHOODS, get_settings
from umbral.database import (
    AnalyzedListingRepository,
    UserListingMatchRepository,
    UserRepository,
    FeedbackRepository,
)
from umbral.config import get_settings
from umbral.models import UserPreferences, HardFilters
from umbral.models.user import SoftPreferences, UserFeedback
from umbral.analysis import EmbeddingGenerator

logger = structlog.get_logger()

# Estados de la conversación
(
    WAITING_OPERATION,
    WAITING_BUDGET,
    WAITING_ROOMS,
    WAITING_DESCRIPTION,
    WAITING_NEIGHBORHOODS_OPTIONAL,
    WAITING_NEIGHBORHOODS,
    WAITING_MUST_HAVES,
) = range(7)


class OnboardingHandler:
    """
    Maneja el flujo de onboarding de usuarios.

    Nuevo flujo simplificado:
    1. Tipo de operación (alquiler/venta)
    2. Presupuesto máximo
    3. Cantidad de ambientes
    4. Descripción en lenguaje natural del hogar ideal
    5. Barrios (opcional)
    6. Must-haves (opcional)
    """

    POPULAR_NEIGHBORHOODS = [
        "Palermo", "Belgrano", "Recoleta", "Caballito",
        "Nuñez", "Villa Crespo", "Colegiales", "Villa Urquiza",
        "Almagro", "Coghlan", "Chacarita", "San Telmo",
    ]

    def __init__(self):
        self.user_repo = UserRepository()
        self.embedding_generator = EmbeddingGenerator()
        self._temp_data: dict = {}  # telegram_id -> data temporal

    def _get_temp_data(self, telegram_id: int) -> dict:
        """Obtiene o inicializa datos temporales para un usuario."""
        if telegram_id not in self._temp_data:
            self._temp_data[telegram_id] = {
                "operation_type": "alquiler",
                "neighborhoods": [],
                "max_price_usd": None,
                "min_rooms": None,
                "max_rooms": None,
                "ideal_description": None,
                "soft_preferences": None,
                "embedding": None,
                "requires_balcony": False,
                "requires_parking": False,
                "requires_furnished": False,
                "requires_pets_allowed": False,
            }
        return self._temp_data[telegram_id]

    def _fix_json(self, text: str) -> str:
        """Arregla JSON malformado (comentarios, comas faltantes)."""
        import re
        
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            if '//' in line:
                pos = line.find('//')
                before = line[:pos]
                quote_count = before.count('"') - before.count('\\"')
                if quote_count % 2 == 0:
                    line = before.rstrip()
            cleaned_lines.append(line)
        
        text = '\n'.join(cleaned_lines)
        
        # Agregar comas faltantes
        text = re.sub(r'(\d+\.?\d*)\s*\n(\s*")', r'\1,\n\2', text)
        text = re.sub(r'(")\s*\n(\s*")', r'\1,\n\2', text)
        text = re.sub(r'(true|false|null)\s*\n(\s*")', r'\1,\n\2', text)
        
        return text

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start - inicia el onboarding."""
        user = update.effective_user
        telegram_id = user.id
        username = user.username

        # Crear o recuperar usuario
        db_user = self.user_repo.get_or_create(telegram_id, username)

        # Inicializar datos temporales
        self._get_temp_data(telegram_id)

        if db_user.get("onboarding_completed"):
            await update.message.reply_text(
                f"¡Hola de nuevo, {user.first_name}! 👋\n\n"
                "Ya tenés tu búsqueda configurada. Usá:\n"
                "• /preferencias - Ver tus preferencias\n"
                "• /pausar - Pausar notificaciones\n"
                "• /reanudar - Reanudar notificaciones\n"
                "• /reset - Reiniciar configuración"
            )
            return ConversationHandler.END

        # Mensaje de bienvenida
        await update.message.reply_text(
            f"¡Hola {user.first_name}! 🏠\n\n"
            "Soy *UMBRAL*, tu asistente de búsqueda inmobiliaria.\n\n"
            "Te voy a hacer algunas preguntas rápidas y después "
            "me vas a contar cómo es tu *hogar ideal*.\n\n"
            "Así voy a poder enviarte *solo* las propiedades que realmente "
            "te pueden interesar. ¿Empezamos?",
            parse_mode="Markdown",
        )

        return await self._ask_operation_type(update, context)

    async def _ask_operation_type(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Paso 1: Tipo de operación."""
        keyboard = [
            [
                InlineKeyboardButton("🔑 Alquiler", callback_data="op_alquiler"),
                InlineKeyboardButton("🏷️ Compra", callback_data="op_venta"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📋 *Paso 1 de 5*\n\n¿Qué tipo de operación buscás?",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return WAITING_OPERATION

    async def handle_operation_type(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa selección de tipo de operación."""
        query = update.callback_query
        await query.answer()

        telegram_id = query.from_user.id
        operation = query.data.replace("op_", "")

        data = self._get_temp_data(telegram_id)
        data["operation_type"] = operation

        self.user_repo.update_onboarding_step(telegram_id, 1)

        await query.edit_message_text(
            f"✅ Perfecto, buscaremos en *{operation}*.",
            parse_mode="Markdown",
        )

        return await self._ask_budget(query, context)

    async def _ask_neighborhoods(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Paso 5: Barrios."""
        telegram_id = query.from_user.id
        data = self._get_temp_data(telegram_id)
        selected = data.get("neighborhoods", [])

        keyboard = []
        row = []

        for barrio in self.POPULAR_NEIGHBORHOODS:
            emoji = "✅ " if barrio in selected else ""
            btn = InlineKeyboardButton(
                f"{emoji}{barrio}",
                callback_data=f"barrio_{barrio}",
            )
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []

        if row:
            keyboard.append(row)

        keyboard.append([
            InlineKeyboardButton("🌆 Todos CABA", callback_data="barrio_todos"),
            InlineKeyboardButton("✔️ Listo", callback_data="barrio_done"),
        ])

        selected_text = ", ".join(selected) if selected else "Ninguno aún"

        await query.message.reply_text(
            f"📋 *Paso 5 de 6*\n\n"
            f"¿En qué barrios te gustaría vivir?\n"
            f"Podés seleccionar varios.\n\n"
            f"Seleccionados: _{selected_text}_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return WAITING_NEIGHBORHOODS

    async def _ask_neighborhoods_optional(
        self, update_or_query, context: ContextTypes.DEFAULT_TYPE
    ):
        """Paso 5: Barrios (opcional)."""
        keyboard = [
            [
                InlineKeyboardButton("📍 Elegir barrios", callback_data="neighopt_choose"),
            ],
            [
                InlineKeyboardButton("🌆 Todos CABA (saltar)", callback_data="neighopt_skip"),
            ],
        ]

        message = update_or_query.message
        await message.reply_text(
            "📋 *Paso 5 de 6 (opcional)*\n\n"
            "¿Querés elegir barrios específicos?\n"
            "Si no, buscamos en toda CABA.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return WAITING_NEIGHBORHOODS_OPTIONAL

    async def handle_neighborhoods_optional(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa selección de barrios (opcional)."""
        query = update.callback_query
        await query.answer()

        telegram_id = query.from_user.id
        action = query.data.replace("neighopt_", "")

        if action == "skip":
            data = self._get_temp_data(telegram_id)
            data["neighborhoods"] = []
            self.user_repo.update_onboarding_step(telegram_id, 5)
            await query.edit_message_text(
                "✅ Barrios: *Todos CABA*",
                parse_mode="Markdown",
            )
            return await self._ask_must_haves(query, context)

        return await self._ask_neighborhoods(query, context)

    async def handle_neighborhood(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa selección de barrios."""
        query = update.callback_query
        await query.answer()

        telegram_id = query.from_user.id
        action = query.data.replace("barrio_", "")

        data = self._get_temp_data(telegram_id)
        selected = data.get("neighborhoods", [])

        if action == "done":
            self.user_repo.update_onboarding_step(telegram_id, 5)
            barrios_text = ", ".join(selected) if selected else "Todos CABA"
            await query.edit_message_text(
                f"✅ Barrios: *{barrios_text}*",
                parse_mode="Markdown",
            )
            return await self._ask_must_haves(query, context)

        if action == "todos":
            data["neighborhoods"] = []
            self.user_repo.update_onboarding_step(telegram_id, 5)
            await query.edit_message_text(
                "✅ Buscaremos en *todos los barrios de CABA*.",
                parse_mode="Markdown",
            )
            return await self._ask_must_haves(query, context)

        # Toggle barrio
        if action in selected:
            selected.remove(action)
        else:
            selected.append(action)

        data["neighborhoods"] = selected

        # Actualizar el mensaje con la nueva selección
        return await self._ask_neighborhoods(query, context)

    async def _ask_budget(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2: Presupuesto."""
        telegram_id = query.from_user.id
        data = self._get_temp_data(telegram_id)
        operation = data.get("operation_type", "alquiler")

        if operation == "venta":
            keyboard = [
                [
                    InlineKeyboardButton("< $100k", callback_data="budget_100000"),
                    InlineKeyboardButton("$100-150k", callback_data="budget_150000"),
                ],
                [
                    InlineKeyboardButton("$150-200k", callback_data="budget_200000"),
                    InlineKeyboardButton("$200-300k", callback_data="budget_300000"),
                ],
                [
                    InlineKeyboardButton("$300-500k", callback_data="budget_500000"),
                    InlineKeyboardButton("> $500k", callback_data="budget_999999"),
                ],
                [
                    InlineKeyboardButton("💰 Sin límite", callback_data="budget_0"),
                ],
            ]
            question = "¿Cuál es tu presupuesto máximo de compra? (en USD)"
        else:
            keyboard = [
                [
                    InlineKeyboardButton("< $400", callback_data="budget_400"),
                    InlineKeyboardButton("$400-600", callback_data="budget_600"),
                ],
                [
                    InlineKeyboardButton("$600-800", callback_data="budget_800"),
                    InlineKeyboardButton("$800-1000", callback_data="budget_1000"),
                ],
                [
                    InlineKeyboardButton("$1000-1500", callback_data="budget_1500"),
                    InlineKeyboardButton("> $1500", callback_data="budget_9999"),
                ],
                [
                    InlineKeyboardButton("💰 Sin límite", callback_data="budget_0"),
                ],
            ]
            question = "¿Cuál es tu presupuesto máximo mensual (alquiler + expensas)? (en USD)"

        await query.message.reply_text(
            "📋 *Paso 2 de 6*\n\n"
            f"{question}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return WAITING_BUDGET

    async def handle_budget(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa selección de presupuesto."""
        query = update.callback_query
        await query.answer()

        telegram_id = query.from_user.id
        budget = int(query.data.replace("budget_", ""))

        data = self._get_temp_data(telegram_id)
        data["max_price_usd"] = budget if budget > 0 else None

        budget_text = f"hasta ${budget} USD" if budget > 0 else "sin límite"
        await query.edit_message_text(
            f"✅ Presupuesto: *{budget_text}*",
            parse_mode="Markdown",
        )

        self.user_repo.update_onboarding_step(telegram_id, 2)
        return await self._ask_rooms(query, context)

    async def _ask_rooms(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3: Cantidad de ambientes."""
        keyboard = [
            [
                InlineKeyboardButton("Monoambiente", callback_data="rooms_1_1"),
                InlineKeyboardButton("2 ambientes", callback_data="rooms_2_2"),
            ],
            [
                InlineKeyboardButton("3 ambientes", callback_data="rooms_3_3"),
                InlineKeyboardButton("4+ ambientes", callback_data="rooms_4_99"),
            ],
            [
                InlineKeyboardButton("2 a 3", callback_data="rooms_2_3"),
                InlineKeyboardButton("3 a 4", callback_data="rooms_3_4"),
            ],
            [
                InlineKeyboardButton("🏠 Cualquiera", callback_data="rooms_0_99"),
            ],
        ]

        await query.message.reply_text(
            "📋 *Paso 3 de 6*\n\n¿Cuántos ambientes necesitás?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return WAITING_ROOMS

    async def handle_rooms(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa selección de ambientes."""
        query = update.callback_query
        await query.answer()

        telegram_id = query.from_user.id
        rooms_data = query.data.replace("rooms_", "").split("_")
        min_rooms = int(rooms_data[0])
        max_rooms = int(rooms_data[1])

        data = self._get_temp_data(telegram_id)
        data["min_rooms"] = min_rooms if min_rooms > 0 else None
        data["max_rooms"] = max_rooms if max_rooms < 99 else None

        if min_rooms == 0:
            rooms_text = "cualquier cantidad"
        elif min_rooms == max_rooms:
            rooms_text = f"{min_rooms} ambiente{'s' if min_rooms > 1 else ''}"
        else:
            rooms_text = f"{min_rooms} a {max_rooms} ambientes"

        await query.edit_message_text(
            f"✅ Ambientes: *{rooms_text}*",
            parse_mode="Markdown",
        )

        self.user_repo.update_onboarding_step(telegram_id, 3)
        return await self._ask_ideal_description(query, context)

    async def _ask_ideal_description(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Paso 4: Descripción del hogar ideal en lenguaje natural."""
        await query.message.reply_text(
            "📋 *Paso 4 de 6 - Tu hogar ideal*\n\n"
            "Ahora contame con tus palabras: *¿Cómo es tu hogar ideal?*\n\n"
            "Por ejemplo:\n"
            "_\"Busco un PH luminoso en zona residencial, ideal para trabajar "
            "desde casa. Me gustaría que tenga techos altos y un estilo moderno "
            "pero cálido. Si tiene patio o terraza, mejor.\"_\n\n"
            "Escribí tu descripción:",
            parse_mode="Markdown",
        )
        return WAITING_DESCRIPTION

    async def handle_ideal_description(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa la descripción del hogar ideal."""
        telegram_id = update.effective_user.id
        description = update.message.text.strip()

        if len(description) < 20:
            await update.message.reply_text(
                "🤔 Tu descripción es muy corta. Contame un poco más sobre "
                "qué tipo de lugar buscás, qué características valorás, "
                "qué ambiente te gustaría...\n\n"
                "Escribí tu descripción:"
            )
            return WAITING_DESCRIPTION

        data = self._get_temp_data(telegram_id)
        data["ideal_description"] = description

        # Mostrar mensaje de procesamiento
        processing_msg = await update.message.reply_text(
            "⏳ Procesando tu descripción..."
        )

        try:
            # Extraer preferencias con Gemini
            soft_prefs = await self._extract_preferences_from_description(description)
            
            # Generar embedding de la descripción
            embedding = await self.embedding_generator.generate_query_embedding(
                description
            )
            data["soft_preferences"] = soft_prefs
            data["embedding"] = embedding
            self.user_repo.update_onboarding_step(telegram_id, 4)

            # Eliminar mensaje de procesamiento
            await processing_msg.delete()

            return await self._ask_neighborhoods_optional(update, context)

        except Exception as e:
            logger.error(
                "Error procesando descripción",
                telegram_id=telegram_id,
                error=str(e),
            )
            await processing_msg.edit_text(
                "❌ Hubo un error procesando tu descripción. "
                "Por favor intentá de nuevo."
            )
            return WAITING_DESCRIPTION

    async def _ask_must_haves(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Paso 6: Must-haves (opcional)."""
        telegram_id = query.from_user.id
        data = self._get_temp_data(telegram_id)

        def flag_text(value: bool, label: str) -> str:
            return f"✅ {label}" if value else label

        keyboard = [
            [
                InlineKeyboardButton(
                    flag_text(data.get("requires_balcony", False), "🏡 Balcón"),
                    callback_data="must_balcony",
                ),
                InlineKeyboardButton(
                    flag_text(data.get("requires_parking", False), "🚗 Cochera"),
                    callback_data="must_parking",
                ),
            ],
            [
                InlineKeyboardButton(
                    flag_text(data.get("requires_furnished", False), "🛋️ Amoblado"),
                    callback_data="must_furnished",
                ),
                InlineKeyboardButton(
                    flag_text(data.get("requires_pets_allowed", False), "🐶 Mascotas"),
                    callback_data="must_pets",
                ),
            ],
            [
                InlineKeyboardButton("✔️ Listo", callback_data="must_done"),
                InlineKeyboardButton("Saltar", callback_data="must_skip"),
            ],
        ]

        await query.message.reply_text(
            "📋 *Paso 6 de 6 (opcional)*\n\n"
            "¿Tenés algún requisito imprescindible?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return WAITING_MUST_HAVES

    async def handle_must_haves(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa selección de must-haves."""
        query = update.callback_query
        await query.answer()

        telegram_id = query.from_user.id
        action = query.data.replace("must_", "")
        data = self._get_temp_data(telegram_id)

        if action in {"balcony", "parking", "furnished", "pets"}:
            key_map = {
                "balcony": "requires_balcony",
                "parking": "requires_parking",
                "furnished": "requires_furnished",
                "pets": "requires_pets_allowed",
            }
            key = key_map[action]
            data[key] = not data.get(key, False)
            return await self._ask_must_haves(query, context)

        if action == "skip":
            data["requires_balcony"] = False
            data["requires_parking"] = False
            data["requires_furnished"] = False
            data["requires_pets_allowed"] = False
            await query.edit_message_text(
                "✅ Requisitos: *Ninguno*",
                parse_mode="Markdown",
            )
        else:
            selected = []
            if data.get("requires_balcony"):
                selected.append("Balcón")
            if data.get("requires_parking"):
                selected.append("Cochera")
            if data.get("requires_furnished"):
                selected.append("Amoblado")
            if data.get("requires_pets_allowed"):
                selected.append("Mascotas")
            text = ", ".join(selected) if selected else "Ninguno"
            await query.edit_message_text(
                f"✅ Requisitos: *{text}*",
                parse_mode="Markdown",
            )

        self.user_repo.update_onboarding_step(telegram_id, 6)
        return await self._complete_onboarding(query, context)

    async def _complete_onboarding(self, query, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = query.from_user.id
        data = self._get_temp_data(telegram_id)

        soft_prefs = data.get("soft_preferences") or SoftPreferences()
        embedding = data.get("embedding") or []
        description = data.get("ideal_description", "")

        hard_filters = HardFilters(
            max_price_usd=data.get("max_price_usd"),
            neighborhoods=data.get("neighborhoods", []),
            min_rooms=data.get("min_rooms"),
            max_rooms=data.get("max_rooms"),
            operation_type=data.get("operation_type", "alquiler"),
            requires_balcony=data.get("requires_balcony", False),
            requires_parking=data.get("requires_parking", False),
            requires_pets_allowed=data.get("requires_pets_allowed", False),
            requires_furnished=data.get("requires_furnished", False),
        )

        soft_prefs.ideal_description = description

        preferences = UserPreferences(
            hard_filters=hard_filters,
            soft_preferences=soft_prefs,
        )

        # Guardar en DB
        self.user_repo.update_preferences(telegram_id, preferences)
        self.user_repo.update_preference_vector(telegram_id, embedding)
        self.user_repo.complete_onboarding(telegram_id)

        # Limpiar datos temporales
        self._temp_data.pop(telegram_id, None)

        barrios = ", ".join(data.get("neighborhoods", [])) or "Todos CABA"
        budget = data.get("max_price_usd")
        budget_text = f"${budget} USD" if budget else "Sin límite"

        min_r = data.get("min_rooms")
        max_r = data.get("max_rooms")
        if min_r and max_r and min_r == max_r:
            rooms_text = f"{min_r} amb."
        elif min_r and max_r:
            rooms_text = f"{min_r}-{max_r} amb."
        elif min_r:
            rooms_text = f"{min_r}+ amb."
        else:
            rooms_text = "Cualquiera"

        must_items = []
        if data.get("requires_balcony"):
            must_items.append("Balcón")
        if data.get("requires_parking"):
            must_items.append("Cochera")
        if data.get("requires_furnished"):
            must_items.append("Amoblado")
        if data.get("requires_pets_allowed"):
            must_items.append("Mascotas")
        must_text = ", ".join(must_items) if must_items else "Ninguno"

        await query.message.reply_text(
            "🎉 *¡Configuración completada!*\n\n"
            f"📍 Barrios: {barrios}\n"
            f"💰 Presupuesto: {budget_text}\n"
            f"🏠 Ambientes: {rooms_text}\n"
            f"✅ Requisitos: {must_text}\n"
            f"🔑 Operación: {data.get('operation_type', 'alquiler').capitalize()}\n\n"
            f"🏡 *Tu hogar ideal:*\n_{description[:200]}{'...' if len(description) > 200 else ''}_\n\n"
            "A partir de ahora te voy a enviar *solo* las propiedades "
            "que matcheen con lo que buscás.\n\n"
            "Cuando recibas una, podés marcarla como:\n"
            "• 👍 *Me interesa* - Para ver más así\n"
            "• 👎 *No es lo que busco* - Para ajustar\n\n"
            "_Usá /preferencias para ver o /reset para cambiar._",
            parse_mode="Markdown",
        )

        logger.info(
            "Onboarding completado con descripción",
            telegram_id=telegram_id,
            description_length=len(description),
        )

        return ConversationHandler.END

    async def _extract_preferences_from_description(
        self, description: str
    ) -> SoftPreferences:
        """
        Usa LLM (Gemini o Groq) para extraer preferencias de la descripción.
        """
        from umbral.analysis import get_llm_provider

        system_prompt = """Eres un experto en análisis de preferencias inmobiliarias.
Tu trabajo es analizar la descripción del hogar ideal de un usuario y extraer 
puntajes de 0.0 a 1.0 para cada preferencia.

Reglas:
- Si el usuario menciona explícitamente algo, dale 0.8-0.9
- Si lo implica, dale 0.6-0.7
- Si no lo menciona, dale 0.5 (neutral)
- Responde SOLO con el JSON, sin texto adicional."""

        user_prompt = f"""DESCRIPCIÓN DEL USUARIO:
"{description}"

Devuelve SOLO un JSON con esta estructura exacta:
{{
    "weight_quietness": 0.0-1.0,
    "weight_luminosity": 0.0-1.0,
    "weight_connectivity": 0.0-1.0,
    "weight_wfh_suitability": 0.0-1.0,
    "weight_modernity": 0.0-1.0,
    "weight_green_spaces": 0.0-1.0
}}"""

        try:
            provider = get_llm_provider()
            response = await provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=256,
            )

            raw_text = response.text.strip()
            
            # Limpiar markdown si viene
            if raw_text.startswith("```"):
                parts = raw_text.split("```")
                if len(parts) >= 2:
                    raw_text = parts[1]
                    if raw_text.startswith("json"):
                        raw_text = raw_text[4:]
            raw_text = raw_text.strip()
            
            # Arreglar JSON malformado
            raw_text = self._fix_json(raw_text)

            data = json.loads(raw_text)

            logger.info(
                "Preferencias extraídas",
                provider=response.provider,
                model=response.model,
            )

            return SoftPreferences(
                weight_quietness=float(data.get("weight_quietness", 0.5)),
                weight_luminosity=float(data.get("weight_luminosity", 0.5)),
                weight_connectivity=float(data.get("weight_connectivity", 0.5)),
                weight_wfh_suitability=float(data.get("weight_wfh_suitability", 0.5)),
                weight_modernity=float(data.get("weight_modernity", 0.5)),
                weight_green_spaces=float(data.get("weight_green_spaces", 0.5)),
            )

        except Exception as e:
            logger.warning(
                "Error extrayendo preferencias, usando defaults",
                error=str(e),
            )
            return SoftPreferences()

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela el onboarding."""
        telegram_id = update.effective_user.id
        self._temp_data.pop(telegram_id, None)
        
        await update.message.reply_text(
            "❌ Configuración cancelada.\n"
            "Podés empezar de nuevo con /start cuando quieras."
        )
        return ConversationHandler.END


class FeedbackHandler:
    """Maneja el feedback de usuarios sobre listings."""

    def __init__(self):
        settings = get_settings()
        self.user_repo = UserRepository()
        self.feedback_repo = FeedbackRepository()
        self.analyzed_repo = AnalyzedListingRepository()
        self.match_repo = UserListingMatchRepository()
        self.learning_rate = settings.feedback_learning_rate

    def _adjust_preference_vector(
        self,
        current_vector: list[float] | None,
        listing_vector: list[float],
        is_like: bool,
    ) -> list[float] | None:
        if not listing_vector:
            return None
        if not current_vector:
            return listing_vector if is_like else None
        common_dim = min(len(current_vector), len(listing_vector))
        if common_dim == 0:
            return None
        if len(current_vector) != len(listing_vector):
            logger.warning(
                "Vector length mismatch; ajustando por dimensión común",
                current_len=len(current_vector),
                listing_len=len(listing_vector),
                common_dim=common_dim,
            )

        current_slice = current_vector[:common_dim]
        listing_slice = listing_vector[:common_dim]
        lr = self.learning_rate
        if is_like:
            adjusted = [
                cur + lr * (target - cur)
                for cur, target in zip(current_slice, listing_slice)
            ]
        else:
            adjusted = [
            cur + lr * (cur - target)
            for cur, target in zip(current_slice, listing_slice)
            ]

        # Conserva la dimensionalidad del vector actual para no romper persistencia.
        if len(current_vector) > common_dim:
            adjusted.extend(current_vector[common_dim:])
        return adjusted

    async def handle_like(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa un 'Me interesa'."""
        query = update.callback_query
        await query.answer("👍 ¡Anotado!")

        telegram_id = query.from_user.id
        analyzed_listing_id = query.data.replace("like_", "")

        user = self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return

        analyzed_listing = self.analyzed_repo.get_by_id(analyzed_listing_id)
        if analyzed_listing and analyzed_listing.get("embedding_vector"):
            new_vector = self._adjust_preference_vector(
                current_vector=user.get("preference_vector"),
                listing_vector=analyzed_listing.get("embedding_vector", []),
                is_like=True,
            )
            if new_vector is not None:
                self.user_repo.update_preference_vector(telegram_id, new_vector)

        feedback = UserFeedback(
            user_id=user["id"],
            analyzed_listing_id=analyzed_listing_id,
            feedback_type="like",
        )

        self.feedback_repo.create(feedback)
        self.match_repo.mark_feedback(user["id"], analyzed_listing_id, "like")
        self.user_repo.increment_feedback_count(telegram_id, is_like=True)

        keyboard = [[InlineKeyboardButton("✅ Te interesa", callback_data="noop")]]
        raw_listing = analyzed_listing.get("raw_listings") if analyzed_listing else None
        if raw_listing and raw_listing.get("url"):
            keyboard.append([
                InlineKeyboardButton("🔗 Ver publicación", url=raw_listing["url"])
            ])

        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        logger.info("Feedback like registrado", telegram_id=telegram_id, listing_id=analyzed_listing_id)

    async def handle_dislike(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Procesa un 'No me interesa'."""
        query = update.callback_query
        await query.answer("👎 Gracias por el feedback")

        telegram_id = query.from_user.id
        analyzed_listing_id = query.data.replace("dislike_", "")

        user = self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return

        analyzed_listing = self.analyzed_repo.get_by_id(analyzed_listing_id)
        if analyzed_listing and analyzed_listing.get("embedding_vector"):
            new_vector = self._adjust_preference_vector(
                current_vector=user.get("preference_vector"),
                listing_vector=analyzed_listing.get("embedding_vector", []),
                is_like=False,
            )
            if new_vector is not None:
                self.user_repo.update_preference_vector(telegram_id, new_vector)

        feedback = UserFeedback(
            user_id=user["id"],
            analyzed_listing_id=analyzed_listing_id,
            feedback_type="dislike",
        )

        self.feedback_repo.create(feedback)
        self.match_repo.mark_feedback(user["id"], analyzed_listing_id, "dislike")
        self.user_repo.increment_feedback_count(telegram_id, is_like=False)

        keyboard = [[InlineKeyboardButton("❌ No te interesa", callback_data="noop")]]
        raw_listing = analyzed_listing.get("raw_listings") if analyzed_listing else None
        if raw_listing and raw_listing.get("url"):
            keyboard.append([
                InlineKeyboardButton("🔗 Ver publicación", url=raw_listing["url"])
            ])

        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        logger.info("Feedback dislike registrado", telegram_id=telegram_id, listing_id=analyzed_listing_id)

    async def handle_noop(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Callback que no hace nada (para botones deshabilitados)."""
        query = update.callback_query
        await query.answer()
