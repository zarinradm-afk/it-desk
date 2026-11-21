from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select



def test_excel_export_permissions_and_values(environment):
    main, auth, models, factory, admin_token, normal_token, _ = environment
    with factory() as db:
        admin = db.scalar(select(models.User).where(models.User.username == "admin-test"))
        asset = models.Asset(tag="EQ-01", name="Printer", asset_type="printer", serial="ABC")
        db.add(asset)
        db.flush()
        db.add(models.Ticket(title="=1+1", description="Printer offline", requester_id=admin.id, asset_id=asset.id))
        db.commit()
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, normal_token)
        assert client.get("/reports/data.xlsx").status_code == 403
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        response = client.get("/reports/data.xlsx")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        book = load_workbook(BytesIO(response.content), data_only=False)
        assert book.sheetnames == ["تیکت‌ها", "دارایی‌ها"]
        assert book["تیکت‌ها"]["B2"].value == "=1+1"
        assert book["تیکت‌ها"]["B2"].data_type == "s"
        assert book["دارایی‌ها"]["B2"].value == "EQ-01"
