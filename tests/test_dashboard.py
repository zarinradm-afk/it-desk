from fastapi.testclient import TestClient
from sqlalchemy import select



def test_dashboard_is_staff_only_and_counts_data(environment):
    main, auth, models, factory, admin_token, normal_token, _ = environment
    with factory() as db:
        admin = db.scalar(select(models.User).where(models.User.username == "admin-test"))
        db.add_all([
            models.Ticket(title="Printer", requester_id=admin.id, status="new", priority="high", category="hardware"),
            models.Ticket(title="Network", requester_id=admin.id, status="resolved", priority="urgent", category="network"),
            models.Asset(tag="PC-01", name="Workstation", asset_type="pc", status="in_use"),
        ])
        db.commit()
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        assert client.get("/dashboard").status_code == 403
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "Printer" in response.text
        assert "Network" in response.text
        assert "<strong>2</strong>" in response.text
        assert "پرتکرارترین دسته‌ها" in response.text
        assert "میانگین زمان رسیدگی" in response.text

def test_dashboard_uses_actual_closure(environment, monkeypatch):
    from datetime import datetime
    main, auth, models, factory, admin, _, uid = environment
    with factory() as db:
        t=models.Ticket(title="duration", requester_id=uid, created_at=datetime(2025,1,1))
        db.add(t)
        db.commit()
        tid=t.id
    url=f"/tickets/{tid}/update"
    with TestClient(main.app) as c:
        c.cookies.set(auth.SESSION_COOKIE,admin)
        c.get("/tickets")
        form={"csrf_token":c.cookies["itdesk_csrf"].split(".")[0]}
        # Freeze only the ticket timestamp, not the session clock.
        class Clock:
            @staticmethod
            def utcnow():
                return datetime(2025,1,2)
        monkeypatch.setattr(main,"closure_now",Clock.utcnow)
        for status, expected in [("closed",24.0),("closed",24.0),("in_progress",None),("resolved",None)]:
            assert c.post(url,data={**form,"status":status},follow_redirects=False).status_code == 303
            assert c.get("/dashboard").context["avg_resolution_hours"] == expected
        monkeypatch.setattr(main,"closure_now",lambda: datetime(2025,1,3))
        c.post(url,data={**form,"status":"closed"})
        assert c.get("/dashboard").context["avg_resolution_hours"] == 48.0
