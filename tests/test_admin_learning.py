from umbral.admin.learning import AdminLearningDashboard


class FakeLearningRepository:
    def snapshot(self, *, window_days: int = 14):
        return {
            "counts": {
                "raw_listings": 10,
                "analyzed_listings": 8,
                "active_analyzed_listings": 7,
            },
            "users": [
                {
                    "id": "user-1",
                    "telegram_id": 100,
                    "telegram_username": "ana",
                    "is_active": True,
                    "onboarding_completed": True,
                    "onboarding_step": 5,
                    "total_likes": 1,
                    "total_dislikes": 0,
                    "created_at": "2026-05-10T10:00:00+00:00",
                    "updated_at": "2026-05-17T10:00:00+00:00",
                    "preferences": {
                        "hard_filters": {
                            "operation_type": "alquiler",
                            "neighborhoods": ["Palermo", "Belgrano"],
                            "max_price_usd": 800,
                            "min_rooms": 2,
                        },
                        "soft_preferences": {
                            "ideal_description": "Luminoso y silencioso",
                        },
                    },
                },
                {
                    "id": "user-2",
                    "telegram_id": 200,
                    "telegram_username": None,
                    "is_active": True,
                    "onboarding_completed": False,
                    "onboarding_step": 2,
                    "total_likes": 0,
                    "total_dislikes": 0,
                    "created_at": "2026-05-11T10:00:00+00:00",
                    "updated_at": "2026-05-11T10:00:00+00:00",
                    "preferences": {},
                },
            ],
            "notifications": [
                {
                    "id": "notif-1",
                    "user_id": "user-1",
                    "analyzed_listing_id": "listing-1",
                    "final_score": 86,
                    "sent_at": "2026-05-16T10:00:00+00:00",
                },
                {
                    "id": "notif-old",
                    "user_id": "user-1",
                    "analyzed_listing_id": "listing-old",
                    "final_score": 80,
                    "sent_at": "2026-04-01T10:00:00+00:00",
                },
            ],
            "feedback": [
                {
                    "id": "fb-1",
                    "user_id": "user-1",
                    "analyzed_listing_id": "listing-1",
                    "feedback_type": "like",
                    "reason": "good_location",
                    "metadata": {},
                    "created_at": "2026-05-16T11:00:00+00:00",
                    "analyzed_listings": {
                        "neighborhood": "Palermo",
                        "rooms": 2,
                        "price_usd": 750,
                        "executive_summary": "Buen depto",
                        "raw_listings": {
                            "title": "Depto en Palermo",
                            "url": "https://example.test/1",
                            "operation_type": "alquiler",
                        },
                    },
                },
                {
                    "id": "fb-old",
                    "user_id": "user-1",
                    "analyzed_listing_id": "listing-old",
                    "feedback_type": "dislike",
                    "reason": "too_expensive",
                    "metadata": {},
                    "created_at": "2026-04-01T11:00:00+00:00",
                    "analyzed_listings": {},
                },
            ],
            "matches": [
                {
                    "id": "match-1",
                    "user_id": "user-1",
                    "analyzed_listing_id": "listing-1",
                    "final_score": 86,
                    "band": "strong",
                    "gaps": ["Presupuesto cerca del limite"],
                    "computed_at": "2026-05-16T09:00:00+00:00",
                    "notified_at": "2026-05-16T10:00:00+00:00",
                    "liked_at": "2026-05-16T11:00:00+00:00",
                    "dismissed_at": None,
                }
            ],
            "ingestion_events": [
                {
                    "id": "event-1",
                    "source": "mercadolibre",
                    "status": "accepted",
                    "quality_score": 82,
                    "reason": "ok",
                    "tags": [],
                    "created_at": "2026-05-16T08:00:00+00:00",
                },
                {
                    "id": "event-2",
                    "source": "mercadolibre",
                    "status": "rejected",
                    "quality_score": 30,
                    "reason": "missing_price",
                    "tags": [],
                    "created_at": "2026-05-16T08:10:00+00:00",
                },
            ],
        }


def test_admin_learning_dashboard_summarizes_mvp_learning_signals():
    dashboard = AdminLearningDashboard(repository=FakeLearningRepository())

    payload = dashboard.build(window_days=14)

    assert payload["summary"]["users_total"] == 2
    assert payload["summary"]["users_onboarded"] == 1
    assert payload["summary"]["analysis_coverage_pct"] == 80.0
    assert payload["summary"]["notifications_sent_window"] == 1
    assert payload["summary"]["feedback_window"] == 1
    assert payload["summary"]["feedback_response_rate_pct"] == 100.0
    assert payload["summary"]["notification_to_like_rate_pct"] == 100.0
    assert payload["feedback_reasons"][0]["label"] == "Buena zona"
    assert payload["users"][0]["telegram_username"] == "ana"
    assert payload["users"][0]["response_rate_pct"] == 100.0
    assert payload["source_quality"][0]["acceptance_rate_pct"] == 50.0
    assert payload["match_quality"]["by_band"] == [{"band": "strong", "count": 1}]
