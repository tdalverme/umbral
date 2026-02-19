"""
Bot principal de Telegram para UMBRAL.

Orquesta los handlers y provee métodos para enviar notificaciones.
"""

from typing import Optional

import structlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from umbral.config import get_settings
from umbral.database import UserRepository
from umbral.bot.handlers import (
    OnboardingHandler,
    FeedbackHandler,
    WAITING_OPERATION,
    WAITING_NEIGHBORHOODS_OPTIONAL,
    WAITING_NEIGHBORHOODS,
    WAITING_BUDGET,
    WAITING_ROOMS,
    WAITING_DESCRIPTION,
    WAITING_MUST_HAVES,
)

logger = structlog.get_logger()


class UmbralBot:
    """
    Bot principal de UMBRAL.

    Responsabilidades:
    - Manejar comandos y callbacks de Telegram
    - Enviar notificaciones de propiedades
    - Gestionar el ciclo de vida del bot
    """

    def __init__(self, token: Optional[str] = None):
        settings = get_settings()
        self.token = token or settings.telegram_bot_token

        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None

        # Handlers
        self.onboarding = OnboardingHandler()
        self.feedback = FeedbackHandler()

        # Repositories
        self.user_repo = UserRepository()

    def setup(self, use_webhook: bool = False) -> Application:
        """Configura la aplicación de Telegram."""
        builder = Application.builder().token(self.token)
        if use_webhook:
            builder = builder.updater(None)
        self.application = builder.build()
        self.bot = self.application.bot

        # ConversationHandler para el onboarding
        onboarding_conv = ConversationHandler(
            entry_points=[CommandHandler("start", self.onboarding.start)],
            states={
                WAITING_OPERATION: [
                    CallbackQueryHandler(
                        self.onboarding.handle_operation_type,
                        pattern=r"^op_",
                    ),
                ],
                WAITING_NEIGHBORHOODS_OPTIONAL: [
                    CallbackQueryHandler(
                        self.onboarding.handle_neighborhoods_optional,
                        pattern=r"^neighopt_",
                    ),
                ],
                WAITING_NEIGHBORHOODS: [
                    CallbackQueryHandler(
                        self.onboarding.handle_neighborhood,
                        pattern=r"^barrio_",
                    ),
                ],
                WAITING_BUDGET: [
                    CallbackQueryHandler(
                        self.onboarding.handle_budget,
                        pattern=r"^budget_",
                    ),
                ],
                WAITING_ROOMS: [
                    CallbackQueryHandler(
                        self.onboarding.handle_rooms,
                        pattern=r"^rooms_",
                    ),
                ],
                WAITING_DESCRIPTION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.onboarding.handle_ideal_description,
                    ),
                ],
                WAITING_MUST_HAVES: [
                    CallbackQueryHandler(
                        self.onboarding.handle_must_haves,
                        pattern=r"^must_",
                    ),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.onboarding.cancel),
                CommandHandler("start", self.onboarding.start),
            ],
            allow_reentry=True,
        )

        self.application.add_handler(onboarding_conv)

        # Otros comandos (fuera del onboarding)
        self.application.add_handler(
            CommandHandler("preferencias", self._show_preferences)
        )
        self.application.add_handler(
            CommandHandler("pausar", self._pause_notifications)
        )
        self.application.add_handler(
            CommandHandler("reanudar", self._resume_notifications)
        )
        self.application.add_handler(
            CommandHandler("reset", self._reset_user)
        )
        self.application.add_handler(
            CommandHandler("help", self._help)
        )

        # Callbacks de feedback (siempre activos)
        self.application.add_handler(
            CallbackQueryHandler(
                self.feedback.handle_like,
                pattern=r"^like_",
            )
        )
        self.application.add_handler(
            CallbackQueryHandler(
                self.feedback.handle_dislike,
                pattern=r"^dislike_",
            )
        )
        self.application.add_handler(
            CallbackQueryHandler(
                self.feedback.handle_noop,
                pattern=r"^noop$",
            )
        )

        # Mensaje por defecto (fuera de conversaciones)
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._default_message,
            )
        )

        logger.info("Bot de Telegram configurado")
        return self.application

    def run(self):
        """Inicia el bot en modo polling."""
        if not self.application:
            self.setup()

        logger.info("Iniciando bot de Telegram...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def send_listing_notification(
        self,
        telegram_id: int,
        listing_data: dict,
        similarity_score: float,
        personalized_analysis: Optional[str] = None,
    ) -> bool:
        """
        Envía una notificación de propiedad a un usuario.

        Args:
            telegram_id: ID de Telegram del usuario
            listing_data: Datos del raw listing
            similarity_score: Score de match (0.0 a 1.0)
            personalized_analysis: Texto personalizado generado con LLM (opcional)

        Returns:
            True si se envió correctamente
        """
        if not self.bot:
            self.bot = Bot(self.token)

        try:
            # Construir mensaje
            raw = listing_data

            # Formatear precio
            price_raw = raw.get("price", 0)
            currency = raw.get("currency", "USD")
            try:
                price_raw = float(str(price_raw).replace(".", "").replace(",", "."))
            except (ValueError, TypeError):
                price_raw = 0

            # Convertir a float de forma segura
            try:
                price_raw = float(price_raw) if price_raw else 0
            except (ValueError, TypeError):
                price_raw = 0

            if currency == "ARS" and price_raw > 0:
                price_text = f"${price_raw:,.0f} ARS"
            else:
                price_text = f"${price_raw:,.0f} USD"

            # Match percentage
            match_pct = int(similarity_score * 100)

            # Emojis por score
            scores = {}
            score_emojis = []
            
            def get_score(key):
                val = scores.get(key, 0)
                try:
                    return float(val) if val else 0
                except (ValueError, TypeError):
                    return 0
            
            if get_score("luminosity") >= 0.7:
                score_emojis.append("☀️")
            if get_score("quietness") >= 0.7:
                score_emojis.append("🤫")
            if get_score("connectivity") >= 0.7:
                score_emojis.append("🚇")
            if get_score("wfh_suitability") >= 0.7:
                score_emojis.append("💻")
            if get_score("green_spaces") >= 0.7:
                score_emojis.append("🌳")

            emojis_text = " ".join(score_emojis) if score_emojis else ""

            # Style tags
            tags = []
            if isinstance(tags, str):
                tags = [tags]
            tags_text = " • ".join([f"#{t}" for t in tags[:3]]) if tags else ""

            analysis_text = personalized_analysis or ""
            if not analysis_text:
                analysis_text = "Propiedad compatible con tu perfil. Revisa la publicacion para confirmar detalles."

            message = (
                f"🏠 *Nueva propiedad encontrada* {emojis_text}\n\n"
                f"📍 *{raw.get('neighborhood', 'CABA')}* • "
                f"{raw.get('rooms', '?')} amb.\n"
                f"💰 {price_text}\n\n"
                f"📝 {analysis_text}\n\n"
                f"{tags_text}\n\n"
                f"🎯 Match: *{match_pct}%*"
            )

            # Botones
            keyboard = [
                [
                    InlineKeyboardButton(
                        "👍 Me interesa",
                        callback_data=f"like_{raw.get('id', '')}",
                    ),
                    InlineKeyboardButton(
                        "👎 No es lo que busco",
                        callback_data=f"dislike_{raw.get('id', '')}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔗 Ver publicación",
                        url=raw.get("url", "#"),
                    ),
                ],
            ]

            # Enviar imagen si hay
            images = raw.get("images", [])
            if images and len(images) > 0:
                try:
                    await self.bot.send_photo(
                        chat_id=telegram_id,
                        photo=images[0],
                        caption=message,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                except Exception:
                    # Si falla la imagen, enviar solo texto
                    await self.bot.send_message(
                        chat_id=telegram_id,
                        text=message,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
            else:
                await self.bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )

            logger.info(
                "Notificación enviada",
                telegram_id=telegram_id,
                listing_id=raw.get("id"),
                match=match_pct,
            )
            return True

        except Exception as e:
            logger.error(
                "Error enviando notificación",
                telegram_id=telegram_id,
                error=str(e),
            )
            return False

    async def _show_preferences(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Muestra las preferencias actuales del usuario."""
        telegram_id = update.effective_user.id
        user = self.user_repo.get_by_telegram_id(telegram_id)

        if not user or not user.get("onboarding_completed"):
            await update.message.reply_text(
                "Todavía no configuraste tus preferencias.\n"
                "Usá /start para comenzar."
            )
            return

        prefs = user.get("preferences", {})
        hard = prefs.get("hard_filters", {})
        soft = prefs.get("soft_preferences", {})

        # Formatear preferencias
        barrios = ", ".join(hard.get("neighborhoods", [])) or "Todos CABA"
        budget = hard.get("max_price_usd")
        budget_text = f"${budget} USD" if budget else "Sin límite"

        min_r = hard.get("min_rooms")
        max_r = hard.get("max_rooms")
        if min_r and max_r:
            rooms_text = f"{min_r} a {max_r}"
        elif min_r:
            rooms_text = f"Mínimo {min_r}"
        elif max_r:
            rooms_text = f"Máximo {max_r}"
        else:
            rooms_text = "Cualquiera"

        # Descripción ideal
        ideal_desc = soft.get("ideal_description", "")
        desc_text = f"\n\n🏡 *Tu hogar ideal:*\n_{ideal_desc[:150]}{'...' if len(ideal_desc) > 150 else ''}_" if ideal_desc else ""

        # Soft preferences
        pref_items = []
        
        def get_weight(key):
            val = soft.get(key, 0)
            try:
                return float(val) if val else 0
            except (ValueError, TypeError):
                return 0
        
        if get_weight("weight_luminosity") >= 0.7:
            pref_items.append("☀️ Luz")
        if get_weight("weight_quietness") >= 0.7:
            pref_items.append("🤫 Silencio")
        if get_weight("weight_connectivity") >= 0.7:
            pref_items.append("🚇 Transporte")
        if get_weight("weight_wfh_suitability") >= 0.7:
            pref_items.append("💻 Home office")
        if get_weight("weight_green_spaces") >= 0.7:
            pref_items.append("🌳 Espacios verdes")
        if get_weight("weight_modernity") >= 0.7:
            pref_items.append("✨ Moderno")

        prefs_text = ", ".join(pref_items) if pref_items else "Balanceadas"

        stats = f"👍 {user.get('total_likes', 0)} likes • 👎 {user.get('total_dislikes', 0)} dislikes"

        await update.message.reply_text(
            f"⚙️ *Tus preferencias actuales*\n\n"
            f"📍 Barrios: {barrios}\n"
            f"💰 Presupuesto: {budget_text}\n"
            f"🏠 Ambientes: {rooms_text}\n"
            f"🔑 Operación: {hard.get('operation_type', 'alquiler').capitalize()}\n\n"
            f"🎯 Priorizás: {prefs_text}"
            f"{desc_text}\n\n"
            f"📊 {stats}\n\n"
            f"_Usá /reset para cambiar tu configuración._",
            parse_mode="Markdown",
        )

    async def _pause_notifications(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Pausa las notificaciones del usuario."""
        telegram_id = update.effective_user.id
        self.user_repo.set_active(telegram_id, False)

        await update.message.reply_text(
            "⏸️ Notificaciones pausadas.\n\n"
            "Usá /reanudar cuando quieras volver a recibir propiedades."
        )

    async def _resume_notifications(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Reanuda las notificaciones del usuario."""
        telegram_id = update.effective_user.id
        self.user_repo.set_active(telegram_id, True)

        await update.message.reply_text(
            "▶️ ¡Notificaciones reactivadas!\n\n"
            "Vas a recibir nuevas propiedades que matcheen con tu búsqueda."
        )

    async def _reset_user(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Reinicia la configuración del usuario."""
        telegram_id = update.effective_user.id

        # Reset onboarding
        self.user_repo.update_onboarding_step(telegram_id, 0)

        await update.message.reply_text(
            "🔄 Configuración reiniciada.\n\n"
            "Usá /start para configurar tus nuevas preferencias."
        )

    async def _help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Muestra ayuda."""
        await update.message.reply_text(
            "🏠 *UMBRAL - Ayuda*\n\n"
            "*Comandos disponibles:*\n"
            "/start - Configurar búsqueda\n"
            "/preferencias - Ver preferencias actuales\n"
            "/pausar - Pausar notificaciones\n"
            "/reanudar - Reanudar notificaciones\n"
            "/reset - Reiniciar configuración\n"
            "/help - Ver esta ayuda\n\n"
            "*¿Cómo funciona?*\n"
            "1. Me contás qué tipo de lugar buscás\n"
            "2. Describís tu hogar ideal con tus palabras\n"
            "3. Analizamos propiedades con IA\n"
            "4. Te enviamos *solo* las que matchean\n"
            "5. Tu feedback mejora las recomendaciones\n\n"
            "_Desarrollado con ❤️ en Buenos Aires_",
            parse_mode="Markdown",
        )

    async def _default_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Responde a mensajes no reconocidos."""
        await update.message.reply_text(
            "🤔 No entendí ese mensaje.\n\n"
            "Usá /help para ver los comandos disponibles."
        )
