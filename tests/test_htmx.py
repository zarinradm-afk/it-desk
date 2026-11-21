from fastapi.testclient import TestClient
from sqlalchemy import select



def test_ticket_status_update_returns_htmx_fragment(environment):
    main, auth, models, factory, admin_token, _, _ = environment
    with factory() as db:
        admin = db.scalar(select(models.User).where(models.User.username == "admin-test"))
        ticket = models.Ticket(title="HTMX ticket", requester_id=admin.id)
        db.add(ticket)
        db.commit()
        ticket_id = ticket.id
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        client.get("/tickets")
        csrf = client.cookies.get("itdesk_csrf").split(".", 1)[0]
        response = client.post(f"/tickets/{ticket_id}/update", headers={"HX-Request": "true"}, data={"csrf_token": csrf, "status": "resolved"})
        assert response.status_code == 200
        assert "حل‌شده" in response.text
        assert "HTMX ticket" not in response.text
