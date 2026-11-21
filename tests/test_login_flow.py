from fastapi.testclient import TestClient
from sqlalchemy import select
from datetime import datetime, timedelta


def test_login_logout_and_ticket_access(environment):
    main, auth, models, factory, _, _, normal_id = environment
    with factory() as db:
        db.add(models.Credential(user_id=normal_id, password_hash=auth.hash_password("a-valid-password")))
        other = models.User(username="other", full_name="Other", role="user")
        db.add(other)
        db.flush()
        db.add(models.Ticket(title="Other ticket", requester_id=other.id))
        db.commit()
        other_ticket = db.scalar(select(models.Ticket.id).where(models.Ticket.title == "Other ticket"))

    with TestClient(main.app) as client:
        assert client.get("/tickets", follow_redirects=False).status_code == 303
        login_page = client.get("/login")
        assert login_page.status_code == 200
        csrf = client.cookies.get("itdesk_csrf").split(".", 1)[0]
        assert client.post("/login", data={"username": "normal-test", "password": "a-valid-password"}).status_code == 403
        login = client.post("/login", data={"csrf_token": csrf, "username": "normal-test", "password": "a-valid-password"}, follow_redirects=False)
        assert login.status_code == 303
        assert "httponly" in login.headers["set-cookie"].lower()
        assert client.get(f"/tickets/{other_ticket}").status_code == 404
        created = client.post("/tickets", data={"csrf_token": csrf, "title": "Own ticket"}, follow_redirects=False)
        assert created.status_code == 303
        own_detail = client.get(created.headers["location"])
        assert own_detail.status_code == 200
        assert "Own ticket" in own_detail.text
        assert client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
        assert client.get("/tickets", follow_redirects=False).status_code == 303


def test_ticket_title_is_required_and_limited(environment):
    main, auth, models, factory, _, normal_token, normal_id = environment
    with factory() as db:
        db.add(models.Credential(user_id=normal_id, password_hash=auth.hash_password("a-valid-password")))
        db.commit()

    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        client.get("/tickets")
        csrf = client.cookies.get("itdesk_csrf").split(".", 1)[0]
        assert client.post("/tickets", data={"csrf_token": csrf, "title": "   "}).status_code == 400
        assert client.post("/tickets", data={"csrf_token": csrf, "title": "x" * 201}).status_code == 400


def test_ticket_filters_and_due_date(environment):
    main, auth, models, factory, _, normal_token, normal_id = environment
    with factory() as db:
        db.add(models.Credential(user_id=normal_id, password_hash=auth.hash_password("a-valid-password")))
        db.add_all([
            models.Ticket(title="Printer issue", requester_id=normal_id, priority="urgent", due_at=datetime.utcnow() - timedelta(hours=1)),
            models.Ticket(title="Laptop request", requester_id=normal_id, priority="low", due_at=datetime.utcnow() + timedelta(hours=72)),
        ])
        db.commit()
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        response = client.get("/tickets?q=Printer&priority=urgent&overdue=1")
        assert response.status_code == 200
        assert "Printer issue" in response.text
        assert "Laptop request" not in response.text
        assert "عقب‌افتاده" in response.text
