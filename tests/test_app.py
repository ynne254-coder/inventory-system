import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3")})
    with app.test_client() as client:
        yield client


def sample_item(**overrides):
    item = {"name": "Tea", "quantity": 5, "price": 2.5, "barcode": "12345", "description": "Black tea"}
    item.update(overrides)
    return item


def test_health_and_empty_list(client):
    assert client.get("/health").get_json() == {"status": "ok"}
    assert client.get("/api/items").get_json() == []


def test_create_read_update_delete_item(client):
    created = client.post("/api/items", json=sample_item())
    assert created.status_code == 201
    item = created.get_json()
    assert item["id"] == 1
    assert item["price"] == 2.5

    assert client.get("/api/items/1").get_json()["name"] == "Tea"
    updated = client.patch("/api/items/1", json={"quantity": 9})
    assert updated.status_code == 200
    assert updated.get_json()["quantity"] == 9
    assert updated.get_json()["name"] == "Tea"

    assert client.delete("/api/items/1").status_code == 200
    assert client.get("/api/items/1").status_code == 404
    assert client.delete("/api/items/1").status_code == 404


def test_validation_and_duplicate_barcode(client):
    assert client.post("/api/items", json={"name": "Tea"}).status_code == 400
    assert client.post("/api/items", json=sample_item(quantity=-1)).status_code == 400
    assert client.post("/api/items", json=sample_item()).status_code == 201
    assert client.post("/api/items", json=sample_item(name="Other")).status_code == 409
    assert client.patch("/api/items/1", json={}).status_code == 400
    assert client.patch("/api/items/999", json={"name": "Tea"}).status_code == 404


def test_openfoodfacts_lookup_by_barcode(client, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": 1, "product": {"product_name": "Chocolate spread", "code": "3017620422003", "brands": "Example", "generic_name": "Hazelnut spread"}}

    def fake_get(url, **kwargs):
        assert url.endswith("/product/3017620422003.json")
        return FakeResponse()

    monkeypatch.setattr("app.requests.get", fake_get)
    response = client.get("/api/products/lookup?barcode=3017620422003")
    assert response.status_code == 200
    assert response.get_json()["name"] == "Chocolate spread"
    assert response.get_json()["brand"] == "Example"


def test_product_import_saves_lookup_result(client, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": 1, "product": {"product_name": "Chocolate spread", "code": "3017620422003", "generic_name": "Hazelnut spread"}}

    monkeypatch.setattr("app.requests.get", lambda *args, **kwargs: FakeResponse())
    response = client.post("/api/products/import", json={"barcode": "3017620422003", "quantity": 4, "price": 3.75})
    assert response.status_code == 201
    assert response.get_json()["name"] == "Chocolate spread"
    assert response.get_json()["quantity"] == 4
    assert client.get("/api/items").get_json()[0]["barcode"] == "3017620422003"


def test_lookup_requires_search_term(client):
    assert client.get("/api/products/lookup").status_code == 400
