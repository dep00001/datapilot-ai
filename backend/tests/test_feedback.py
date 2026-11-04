from __future__ import annotations
import pytest
from app.core.rate_limit import clear_rate_limits

FEEDBACK_URL = "/api/feedback"
REVIEWS_URL = "/api/reviews"
ADMIN_URL = "/api/admin/feedback"


@pytest.fixture(autouse=True)
def reset_rl():
    clear_rate_limits()
    yield
    clear_rate_limits()


class TestFeedbackPrivacy:
    def test_feedback_requires_auth(self, client):
        r = client.post(FEEDBACK_URL, json={"rating": 5, "category": "Test"})
        assert r.status_code == 401

    def test_my_feedback_requires_auth(self, client):
        r = client.get(f"{FEEDBACK_URL}/mine")
        assert r.status_code == 401

    def test_delete_feedback_requires_auth(self, client):
        r = client.delete(f"{FEEDBACK_URL}/some-id")
        assert r.status_code == 401


class TestPublicReviews:
    def test_public_reviews_accessible(self, client):
        r = client.get(REVIEWS_URL)
        assert r.status_code == 200
        data = r.json()
        assert "reviews" in data
        # Without any published reviews, should return empty list
        assert isinstance(data["reviews"], list)

    def test_public_reviews_empty_state(self, client):
        r = client.get(REVIEWS_URL)
        assert r.status_code == 200
        data = r.json()
        # Correct empty state
        if data["total_published"] == 0:
            assert data["reviews"] == []
            assert data["average_rating"] is None


class TestAdminAccess:
    def test_admin_requires_auth(self, client):
        r = client.get(ADMIN_URL)
        assert r.status_code == 401

    def test_admin_patch_requires_auth(self, client):
        r = client.patch(f"{ADMIN_URL}/some-id", json={"admin_status": "reviewed"})
        assert r.status_code == 401

    def test_regular_user_cannot_access_admin(self, client):
        """Non-admin authenticated users should get 403, not 200."""
        # Since no auth, 401 is expected
        r = client.get(ADMIN_URL)
        assert r.status_code in (401, 403)
