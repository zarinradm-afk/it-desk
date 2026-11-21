from fastapi.testclient import TestClient
from sqlalchemy import select


def test_admin_management_and_reset_invalidates_existing_session(environment):
    main, auth, models, factory, admin_token, normal_token, normal_id = environment
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        assert client.get("/admin/users").status_code == 403
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        assert client.get("/admin/users").status_code == 200
        csrf = client.cookies.get("itdesk_csrf").split(".", 1)[0]
        assert f'name="csrf_token" value="{csrf}"' in client.get("/admin/users").text
        assert client.post("/admin/users", data={"username": "blocked", "full_name": "Blocked", "role": "user"}).status_code == 403
        assert client.post("/admin/users", data={"username": "blocked", "full_name": "Blocked", "role": "user", "csrf_token": "invalid"}).status_code == 403
        assert client.post("/admin/users", data={"username": "blocked", "full_name": "Blocked", "role": "user", "csrf_token": "نامعتبر"}).status_code == 403
        created = client.post("/admin/users", data={"username": "new-user", "full_name": "New User", "role": "agent", "password": "test-password", "csrf_token": csrf})
        assert created.status_code == 200
        assert created.headers["cache-control"] == "no-store"
        assert "test-password" not in created.text
        assert client.post("/admin/users", data={"username": "short-pass", "full_name": "Short", "role": "user", "password": "short", "csrf_token": csrf}).status_code == 400
        assert client.post("/admin/users", data={"username": "new-user", "full_name": "Duplicate", "role": "user", "csrf_token": csrf}).status_code == 409
        reset = client.post(f"/admin/users/{normal_id}/reset-password", data={"csrf_token": csrf})
        assert reset.status_code == 200
        assert reset.headers["cache-control"] == "no-store"
        with factory() as db:
            assert db.scalar(select(models.LoginSession).where(models.LoginSession.user_id == normal_id)) is None
            assert db.scalar(select(models.AuditLog).where(models.AuditLog.action == "reset_password")) is not None
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        assert client.get("/tickets", follow_redirects=False).status_code == 303


def test_only_active_admin_cannot_be_demoted_or_deactivated(environment):
    main, auth, models, factory, admin_token, _, _ = environment
    with factory() as db:
        admin_id = db.scalar(select(models.User.id).where(models.User.role == "admin"))
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        client.get("/admin/users")
        csrf = client.cookies.get("itdesk_csrf").split(".", 1)[0]
        assert client.post(f"/admin/users/{admin_id}/update", data={"full_name": "Admin", "role": "user", "is_active": "1", "csrf_token": csrf}).status_code == 400
        assert client.post(f"/admin/users/{admin_id}/update", data={"full_name": "Admin", "role": "admin", "csrf_token": csrf}).status_code == 400


def test_deactivating_and_reactivating_user_does_not_restore_old_session(environment):
    main, auth, models, factory, admin_token, normal_token, normal_id = environment
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        client.get("/admin/users")
        csrf = client.cookies.get("itdesk_csrf").split(".", 1)[0]
        form = {"full_name": "Normal", "role": "user", "csrf_token": csrf}
        assert client.post(f"/admin/users/{normal_id}/update", data=form, follow_redirects=False).status_code == 303
        form["is_active"] = "1"
        assert client.post(f"/admin/users/{normal_id}/update", data=form, follow_redirects=False).status_code == 303
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        assert client.get("/tickets", follow_redirects=False).status_code == 303


def test_user_changes_own_password_and_old_session_is_revoked(environment):
    main, auth, models, factory, _, normal_token, normal_id = environment
    with factory() as db:
        db.add(models.Credential(user_id=normal_id, password_hash=auth.hash_password("original-password")))
        db.commit()
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        page = client.get("/account/password")
        assert page.status_code == 200
        csrf = client.cookies.get("itdesk_csrf").split(".", 1)[0]
        form = {"csrf_token": csrf, "current_password": "wrong", "new_password": "new-password-123", "confirm_password": "new-password-123"}
        assert client.post("/account/password", data=form).status_code == 400
        form["current_password"] = "original-password"
        form["confirm_password"] = "different-password"
        assert client.post("/account/password", data=form).status_code == 400
        form["confirm_password"] = form["new_password"]
        response = client.post("/account/password", data=form, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["cache-control"] == "no-store"
        with factory() as db:
            cred = db.get(models.Credential, normal_id)
            assert auth.verify_password("new-password-123", cred.password_hash)
            assert db.scalar(select(models.LoginSession).where(models.LoginSession.user_id == normal_id)) is None
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        assert client.get("/tickets", follow_redirects=False).status_code == 303
