def test_static_shell(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert r.headers["cache-control"] == "no-cache"
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/app.css").status_code == 200


def test_api_still_protected_and_unknown_404(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/nimportequoi").status_code == 404
