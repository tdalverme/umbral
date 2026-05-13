from umbral.models.user import UserFeedback


def test_user_feedback_accepts_optional_reason_and_metadata():
    feedback = UserFeedback(
        user_id="user-1",
        analyzed_listing_id="listing-1",
        feedback_type="dislike",
        reason="too_expensive",
        metadata={"source": "telegram"},
    )

    data = feedback.to_db_dict()

    assert data["reason"] == "too_expensive"
    assert data["metadata"] == {"source": "telegram"}


def test_user_feedback_keeps_existing_minimal_shape_compatible():
    feedback = UserFeedback(
        user_id="user-1",
        analyzed_listing_id="listing-1",
        feedback_type="like",
    )

    data = feedback.to_db_dict()

    assert data["feedback_type"] == "like"
    assert data["reason"] is None
    assert data["metadata"] == {}
