from types import SimpleNamespace

import pytest

from umbral.bot.handlers import FeedbackHandler


class FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=123)
        self.answers = []
        self.reply_markup = None

    async def answer(self, text=None):
        self.answers.append(text)

    async def edit_message_reply_markup(self, reply_markup=None):
        self.reply_markup = reply_markup


class FakeUserRepo:
    def __init__(self):
        self.updated_vectors = []
        self.likes = 0
        self.dislikes = 0

    def get_by_telegram_id(self, telegram_id):
        return {"id": "user-1", "preference_vector": [0.1, 0.2]}

    def update_preference_vector(self, telegram_id, vector):
        self.updated_vectors.append(vector)

    def increment_feedback_count(self, telegram_id, is_like):
        if is_like:
            self.likes += 1
        else:
            self.dislikes += 1


class FakeFeedbackRepo:
    def __init__(self):
        self.created = []
        self.reasons = []

    def create(self, feedback):
        self.created.append(feedback)
        return feedback.to_db_dict()

    def update_reason(self, user_id, analyzed_listing_id, reason, metadata=None):
        self.reasons.append((user_id, analyzed_listing_id, reason, metadata or {}))
        return {}


class FakeAnalyzedRepo:
    def __init__(self, listing=None):
        self.listing = listing or {
            "id": "listing-1",
            "embedding_vector": None,
            "raw_listings": {"url": "https://example.test/listing"},
        }

    def get_by_id(self, analyzed_listing_id):
        return self.listing


class FakeMatchRepo:
    def __init__(self):
        self.feedback = []

    def mark_feedback(self, user_id, analyzed_listing_id, feedback_type):
        self.feedback.append((user_id, analyzed_listing_id, feedback_type))
        return True


def _handler(analyzed_listing=None):
    handler = FeedbackHandler.__new__(FeedbackHandler)
    handler.user_repo = FakeUserRepo()
    handler.feedback_repo = FakeFeedbackRepo()
    handler.analyzed_repo = FakeAnalyzedRepo(analyzed_listing)
    handler.match_repo = FakeMatchRepo()
    handler.learning_rate = 0.1
    return handler


def _button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callback_data(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


@pytest.mark.asyncio
async def test_like_registers_feedback_and_shows_optional_reason_buttons():
    handler = _handler()
    query = FakeQuery("like_listing-1")
    update = SimpleNamespace(callback_query=query)

    await handler.handle_like(update, None)

    assert handler.feedback_repo.created[0].feedback_type == "like"
    assert handler.match_repo.feedback == [("user-1", "listing-1", "like")]
    assert "Buena zona" in _button_texts(query.reply_markup)
    assert "Contactar/visitar" in _button_texts(query.reply_markup)
    assert "feedback_reason_l_gl_listing-1" in _callback_data(query.reply_markup)


@pytest.mark.asyncio
async def test_dislike_registers_feedback_and_shows_optional_reason_buttons():
    handler = _handler()
    query = FakeQuery("dislike_listing-1")
    update = SimpleNamespace(callback_query=query)

    await handler.handle_dislike(update, None)

    assert handler.feedback_repo.created[0].feedback_type == "dislike"
    assert handler.match_repo.feedback == [("user-1", "listing-1", "dislike")]
    assert "Muy caro" in _button_texts(query.reply_markup)
    assert "Ya lo vi" in _button_texts(query.reply_markup)
    assert "feedback_reason_d_te_listing-1" in _callback_data(query.reply_markup)


@pytest.mark.asyncio
async def test_feedback_reason_updates_existing_feedback_without_new_feedback():
    handler = _handler()
    query = FakeQuery("feedback_reason_d_te_listing-1")
    update = SimpleNamespace(callback_query=query)

    await handler.handle_reason(update, None)

    assert handler.feedback_repo.created == []
    assert handler.feedback_repo.reasons == [
        ("user-1", "listing-1", "too_expensive", {"feedback_type": "dislike"})
    ]
    assert "Anotado: muy caro" in _button_texts(query.reply_markup)


@pytest.mark.asyncio
async def test_already_seen_reason_does_not_adjust_preference_vector():
    handler = _handler(
        {
            "id": "listing-1",
            "embedding_vector": [0.8, 0.9],
            "raw_listings": {"url": "https://example.test/listing"},
        }
    )
    query = FakeQuery("feedback_reason_dislike_already_seen_listing-1")
    update = SimpleNamespace(callback_query=query)

    await handler.handle_reason(update, None)

    assert handler.user_repo.updated_vectors == []
