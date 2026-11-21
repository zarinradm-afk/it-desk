import importlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main = importlib.import_module("app.main")
    from app import auth, models
    from app.database import Base, get_db

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)

    def override_db():
        with factory() as db:
            yield db

    main.app.dependency_overrides[get_db] = override_db
    with factory() as db:
        admin = models.User(username="admin-test", full_name="Admin", role="admin")
        normal = models.User(username="normal-test", full_name="Normal", role="user")
        db.add_all([admin, normal])
        db.commit()
        admin_token = auth.create_session(db, admin)
        normal_token = auth.create_session(db, normal)
        normal_id = normal.id
    yield main, auth, models, factory, admin_token, normal_token, normal_id
    main.app.dependency_overrides.clear()
    engine.dispose()
