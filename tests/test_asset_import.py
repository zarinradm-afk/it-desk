from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select


def _workbook(rows):
    book = Workbook()
    sheet = book.active
    sheet.append(["شماره اموال", "نام", "نوع", "سریال", "وضعیت", "نام کاربری تحویل‌گیرنده"])
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    output.seek(0)
    return output


def test_bulk_asset_import(environment):
    main, auth, models, factory, admin_token, _, _ = environment
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        client.get("/assets")
        csrf = client.cookies["itdesk_csrf"].split(".")[0]
        response = client.post("/assets/import", data={"csrf_token": csrf}, files={"file": ("assets.xlsx", _workbook([
            ["EQ-BULK-01", "لپ‌تاپ واحد IT", "laptop", "SN-001", "in_use", ""],
            ["EQ-BULK-02", "سوئیچ شبکه", "switch", "SN-002", "storage", "admin-test"],
        ]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, follow_redirects=False)
        assert response.status_code == 303
        assert "imported=2" in response.headers["location"]
        with factory() as db:
            assert db.scalar(select(models.Asset).where(models.Asset.tag == "EQ-BULK-02")).assigned_to.username == "admin-test"


def test_bulk_asset_import_is_atomic_on_duplicate(environment):
    main, auth, models, factory, admin_token, _, _ = environment
    with TestClient(main.app) as client:
        client.cookies.set(auth.SESSION_COOKIE, admin_token)
        client.get("/assets")
        csrf = client.cookies["itdesk_csrf"].split(".")[0]
        response = client.post("/assets/import", data={"csrf_token": csrf}, files={"file": ("assets.xlsx", _workbook([
            ["EQ-ATOMIC-01", "اول", "laptop", "", "in_use", ""],
            ["EQ-ATOMIC-01", "تکراری", "laptop", "", "in_use", ""],
        ]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert response.status_code == 409
        with factory() as db:
            assert db.scalar(select(models.Asset).where(models.Asset.tag == "EQ-ATOMIC-01")) is None

def test_import_100_rows_search_and_edit(environment):
    main, auth, models, factory, admin, normal, _ = environment
    rows = [[f"DEMO-{i:03}", f"Printer {i}", "printer", f"SN-{i}", "storage", "", f"Room-{i:03}"] for i in range(100)]
    book = Workbook()
    book.active.append(["شماره اموال", "نام", "نوع", "سریال", "وضعیت", "نام کاربری تحویل‌گیرنده", "محل"])
    for row in rows:
        book.active.append(row)
    data = BytesIO()
    book.save(data)
    with TestClient(main.app) as c:
        c.cookies.set(auth.SESSION_COOKIE, admin)
        c.get("/assets")
        csrf = {"csrf_token": c.cookies["itdesk_csrf"].split(".")[0]}
        result = c.post("/assets/import", data=csrf, files={"file": ("sample.xlsx", data.getvalue())}, follow_redirects=False)
        assert result.headers["location"] == "/assets?imported=100"
        with factory() as db:
            assets = db.scalars(select(models.Asset).order_by(models.Asset.tag)).all()
            assert [(a.tag,a.name,a.location) for a in assets] == [(r[0],r[1],r[6]) for r in rows]
            aid = assets[-1].id
        for q in ("DEMO-099", "Printer 99", "Room-099"):
            page = c.get("/assets", params={"q":q}).text
            assert f'href="/assets/{aid}"' in page and "DEMO-098" not in page
        url = f"/assets/{aid}/location"
        assert "New room" in c.post(url,data={**csrf,"location":"New room"}).text
        assert "DEMO-099" not in c.get("/assets?q=Room-099").text
        c.cookies.set(auth.SESSION_COOKIE, normal)
        assert c.post(url,data={**csrf,"location":"Denied"}).status_code == 403
