from fastapi.testclient import TestClient
from sqlalchemy import select

def test_phone_intake_ownership_audit_and_waiting(environment):
    main, auth, models, factory, admin, normal, person = environment
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, normal)
        client.get("/tickets")
        form = dict(csrf_token=client.cookies["itdesk_csrf"].split(".")[0], title="Phone intake", category="network", caller_id=str(person))
        assert client.post("/tickets", data=form).status_code == 403
        client.cookies.set(auth.SESSION_COOKIE, admin)
        assert client.post("/tickets", data={**form, "caller_id": "999999"}).status_code == 400
        response = client.post("/tickets", data=form, follow_redirects=False)
        assert response.status_code == 303
        url = response.headers["location"]
        assert client.post(url+"/update", data={"csrf_token": form["csrf_token"], "status":"waiting"}, follow_redirects=False).status_code == 303
        client.cookies.set(auth.SESSION_COOKIE, normal)
        assert client.get(url).status_code == 200
        assert "Phone intake" in client.get("/tickets?status=waiting").text
        with factory() as db:
            ticket=db.scalar(select(models.Ticket).where(models.Ticket.title=="Phone intake"))
            assert (ticket.requester_id,ticket.intake,ticket.category)==(person,"phone","network")
            actor=db.scalar(select(models.AuditLog.actor_id).where(models.AuditLog.entity_id==ticket.id, models.AuditLog.action=="create"))
            assert actor==db.scalar(select(models.User.id).where(models.User.username=="admin-test"))
