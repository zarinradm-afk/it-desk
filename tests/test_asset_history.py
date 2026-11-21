from fastapi.testclient import TestClient
from sqlalchemy import select


def test_asset_detail_shows_related_tickets(environment):
    main, auth, models, factory, admin_token, _, _ = environment
    with factory() as db:
        admin = db.scalar(select(models.User).where(models.User.username == "admin-test"))
        asset = models.Asset(tag="EQ-HISTORY", name="Printer", asset_type="printer")
        db.add(asset)
        db.flush()
        db.add(models.Ticket(title="Printer outage", requester_id=admin.id, asset_id=asset.id, category="hardware"))
        db.commit()
        asset_id = asset.id
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        response = client.get(f"/assets/{asset_id}")
        assert response.status_code == 200
        assert "Printer outage" in response.text
        assert "تاریخچهٔ تیکت‌های مرتبط" in response.text
