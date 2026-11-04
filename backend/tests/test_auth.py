from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from app.core.rate_limit import clear_rate_limits

REGISTER_URL = "/api/auth/register"
VERIFY_URL = "/api/auth/verify-email"
LOGIN_URL = "/api/auth/login"
ME_URL = "/api/auth/me"
LOGOUT_URL = "/api/auth/logout"
FORGOT_URL = "/api/auth/forgot-password"
RESET_URL = "/api/auth/reset-password"
RESEND_URL = "/api/auth/resend-otp"


def make_user(suffix=""):
    return {
        "name": f"Test User{suffix}",
        "email": f"testuser{suffix}@example.com",
        "password": "SecurePassword123!",
        "confirm_password": "SecurePassword123!",
    }


@pytest.fixture(autouse=True)
def reset_rate_limits():
    clear_rate_limits()
    yield
    clear_rate_limits()


class TestRegistration:
    def test_register_success(self, client):
        r = client.post(REGISTER_URL, json=make_user("_reg1"))
        # Should work (202) or fail with email error (502/503) but NOT 4xx logic errors
        assert r.status_code in (200, 502, 503), r.text

    def test_register_password_mismatch(self, client):
        data = make_user("_mismatch")
        data["confirm_password"] = "DifferentPassword999!"
        r = client.post(REGISTER_URL, json=data)
        assert r.status_code == 422

    def test_register_short_password(self, client):
        data = make_user("_short")
        data["password"] = "short"
        data["confirm_password"] = "short"
        r = client.post(REGISTER_URL, json=data)
        assert r.status_code == 422

    def test_register_invalid_email(self, client):
        data = make_user("_bad")
        data["email"] = "not-an-email"
        r = client.post(REGISTER_URL, json=data)
        assert r.status_code == 422

    def test_register_short_name(self, client):
        data = make_user("_n")
        data["name"] = "A"
        r = client.post(REGISTER_URL, json=data)
        assert r.status_code == 422


class TestEmailVerification:
    def test_verify_wrong_code(self, client):
        r = client.post(VERIFY_URL, json={"email": "nobody@example.com", "code": "000000"})
        assert r.status_code == 400

    def test_verify_invalid_code_format(self, client):
        r = client.post(VERIFY_URL, json={"email": "test@example.com", "code": "abc"})
        assert r.status_code == 422

    def test_verify_5digit_code_rejected(self, client):
        r = client.post(VERIFY_URL, json={"email": "test@example.com", "code": "12345"})
        assert r.status_code == 422


class TestLogin:
    def test_login_nonexistent_user(self, client):
        r = client.post(LOGIN_URL, json={"email": "ghost@example.com", "password": "SomePassword123!"})
        assert r.status_code == 401

    def test_login_wrong_password(self, client):
        r = client.post(LOGIN_URL, json={"email": "testuser@example.com", "password": "WrongPassword999!"})
        assert r.status_code == 401

    def test_login_empty_password(self, client):
        r = client.post(LOGIN_URL, json={"email": "test@example.com", "password": ""})
        assert r.status_code == 422

    def test_unauthenticated_me(self, client):
        r = client.get(ME_URL)
        assert r.status_code == 401


class TestPasswordRecovery:
    def test_forgot_nonexistent_email(self, client):
        r = client.post(FORGOT_URL, json={"email": "ghost@example.com"})
        # Must always return 200 to prevent enumeration
        assert r.status_code == 200

    def test_reset_wrong_code(self, client):
        r = client.post(RESET_URL, json={
            "email": "nobody@example.com",
            "code": "999999",
            "new_password": "NewSecure123!x",
            "confirm_password": "NewSecure123!x",
        })
        assert r.status_code == 400

    def test_reset_password_mismatch(self, client):
        r = client.post(RESET_URL, json={
            "email": "test@example.com",
            "code": "123456",
            "new_password": "SecureNewPassword123!",
            "confirm_password": "DifferentPassword456!",
        })
        assert r.status_code == 422

    def test_reset_short_new_password(self, client):
        r = client.post(RESET_URL, json={
            "email": "test@example.com",
            "code": "123456",
            "new_password": "short",
            "confirm_password": "short",
        })
        assert r.status_code == 422


class TestPasswordSecurity:
    def test_argon2id_produces_hash(self):
        from app.core.security import hash_password, verify_password
        h = hash_password("MySecurePassword123!")
        assert h.startswith("$argon2")
        assert verify_password(h, "MySecurePassword123!") is True
        assert verify_password(h, "WrongPassword") is False

    def test_plaintext_password_not_stored(self):
        """Verify hash does not contain raw password string."""
        from app.core.security import hash_password
        pw = "MyUnique$ecurePassword123!"
        h = hash_password(pw)
        assert pw not in h


class TestOTPSecurity:
    def test_otp_digest_different_from_raw(self):
        from app.core.security import otp_digest
        code = "123456"
        digest = otp_digest(code)
        assert digest != code
        assert len(digest) == 64  # SHA256 hex

    def test_otp_verify_correct(self):
        from app.core.security import otp_digest, verify_otp_digest
        code = "654321"
        d = otp_digest(code)
        assert verify_otp_digest(code, d) is True

    def test_otp_verify_wrong_code(self):
        from app.core.security import otp_digest, verify_otp_digest
        code = "654321"
        d = otp_digest(code)
        assert verify_otp_digest("000000", d) is False

    def test_otp_6_digits(self):
        from app.core.security import generate_otp
        for _ in range(20):
            otp = generate_otp()
            assert len(otp) == 6
            assert otp.isdigit()


class TestSessionSecurity:
    def test_token_digest_sha256(self):
        from app.core.security import token_digest, generate_session_token
        tok = generate_session_token()
        digest = token_digest(tok)
        assert digest != tok
        assert len(digest) == 64

    def test_unauthenticated_dataset_access(self, client):
        r = client.get("/api/datasets")
        assert r.status_code == 401

    def test_unauthenticated_upload(self, client):
        r = client.post("/api/datasets/upload", files={"file": ("test.csv", b"a,b\n1,2", "text/csv")})
        assert r.status_code == 401

    def test_unauthenticated_feedback(self, client):
        r = client.post("/api/feedback", json={"rating": 5, "category": "Test"})
        assert r.status_code == 401

    def test_unauthenticated_admin(self, client):
        r = client.get("/api/admin/feedback")
        assert r.status_code == 401
