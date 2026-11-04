from __future__ import annotations
import io
import os
import pytest
from fastapi.testclient import TestClient

# Use in-memory SQLite for tests, separate from dev DB
os.environ["DATABASE_URL"] = "sqlite:///./test_datapilot.db"
os.environ["APP_SECRET_KEY"] = "test_secret_key_for_pytest_only_not_production_use"
os.environ["EMAIL_PROVIDER"] = "resend"
os.environ["RESEND_API_KEY"] = ""  # No real emails in tests
os.environ["APP_ENV"] = "development"  # Enables console fallback for email

from app.main import app
from app.models import init_db, engine, Base

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c

def sample_csv() -> bytes:
    return b"""Company,Revenue,Employees,Founded
Apple,383285,161000,1976
Google,307394,182502,1998
Microsoft,211915,221000,1975
Amazon,574785,1525000,1994
Meta,134902,67317,2004
"""

def sample_csv_with_issues() -> bytes:
    return b"""Name,Score,Category
  Alice  ,85,A
Bob,  90,B
Alice,85,A
Charlie,,C
Dave,70,
"""
