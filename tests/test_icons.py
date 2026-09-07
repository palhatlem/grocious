import io
from PIL import Image


def test_icon_assets(client):
    page = client.get("/").text
    assert "grocious-icon.svg?v=2" in page
    ico = client.get("/favicon.ico")
    assert ico.status_code == 200 and ico.mimetype == "image/vnd.microsoft.icon"
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= Image.open(io.BytesIO(ico.data)).ico.sizes()
    for icon in client.get("/manifest.webmanifest").json["icons"]:
        response = client.get(icon["src"])
        assert response.status_code == 200
        size = tuple(map(int, icon["sizes"].split("x")))
        assert Image.open(io.BytesIO(response.data)).size == size
    apple = client.get("/static/brand/apple-touch-icon.png")
    assert Image.open(io.BytesIO(apple.data)).size == (180, 180)
