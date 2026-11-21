from fastapi.testclient import TestClient



def test_local_font_is_served_without_external_cdn(environment):
    main, _, _, _, _, _, _ = environment
    with TestClient(main.app) as client:
        response = client.get("/static/fonts/Vazirmatn-Regular.woff2")
        assert response.status_code == 200
        assert response.headers["content-type"] == "font/woff2"
        assert response.content[:4] == b"wOF2"
        login = client.get("/login")
        assert "https://cdn.jsdelivr.net" not in login.text
        assert "/static/fonts/Vazirmatn-Regular.woff2" in login.text
        htmx = client.get("/static/js/htmx.min.js")
        assert htmx.status_code == 200
        assert b"htmx" in htmx.content[:5000]
