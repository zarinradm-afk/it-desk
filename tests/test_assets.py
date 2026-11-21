from sqlalchemy import select
from fastapi.testclient import TestClient


def test_staff_can_create_asset_and_link_ticket(environment):
    main, auth, models, factory, admin_token, normal_token, _ = environment
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        assert client.get("/assets").status_code == 403
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        assert client.get("/assets").status_code == 200
        csrf = client.cookies.get("itdesk_csrf").split(".", 1)[0]
        created = client.post("/assets", data={
            "csrf_token": csrf,
            "tag": "IT-001",
            "name": "Dell Latitude",
            "asset_type": "laptop",
            "serial": "SN-001",
            "status": "in_use",
            "assigned_to_id": "",
        }, follow_redirects=False)
        assert created.status_code == 303
        with factory() as db:
            asset = db.scalar(select(models.Asset).where(models.Asset.tag == "IT-001"))
            assert asset is not None
            asset_id = asset.id
        response = client.post("/tickets", data={"csrf_token": csrf, "title": "Laptop issue", "asset_id": str(asset_id)}, follow_redirects=False)
        assert response.status_code == 303
        ticket_url = response.headers["location"]
        detail = client.get(ticket_url)
        assert detail.status_code == 200
        assert "IT-001" in detail.text
        response = client.post(ticket_url + "/update", data={"csrf_token": csrf, "status": "in_progress"}, follow_redirects=False)
        assert response.status_code == 303
        with factory() as db:
            ticket = db.scalar(select(models.Ticket).where(models.Ticket.title == "Laptop issue"))
            assert ticket.asset_id == asset_id
        response = client.post(ticket_url + "/update", data={"csrf_token": csrf, "status": "in_progress", "asset_id": ""}, follow_redirects=False)
        assert response.status_code == 303
        assert "شناسه دارایی" in client.get(ticket_url).text
        with factory() as db:
            ticket = db.scalar(select(models.Ticket).where(models.Ticket.title == "Laptop issue"))
            assert ticket.asset_id is None
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        response = client.post("/tickets", data={"csrf_token": csrf, "title": "Forbidden", "asset_id": str(asset_id)})
        assert response.status_code == 403
