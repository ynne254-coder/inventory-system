"""Flask REST API for a small inventory management system."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import requests
from flask import Flask, current_app, g, jsonify, request


def get_db() -> sqlite3.Connection:
    """Get this request's database connection, creating it when needed."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def init_db() -> None:
    """Create the inventory table if this is a new database."""
    db = get_db()
    db.execute(
        """CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity >= 0),
            price REAL NOT NULL CHECK (price >= 0),
            barcode TEXT UNIQUE,
            description TEXT NOT NULL DEFAULT ''
        )"""
    )
    db.commit()


def close_db(_error: BaseException | None = None) -> None:
    """Close the request's database connection at the end of a request."""
    from flask import g

    db = g.pop("db", None)
    if db is not None:
        db.close()


def item_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def validate_item(data: Any, partial: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    """Validate incoming JSON and return cleaned fields or an error message."""
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object."

    required = {"name", "quantity", "price"}
    allowed = required | {"barcode", "description"}
    if not partial:
        missing = required - data.keys()
        if missing:
            return None, f"Missing required field(s): {', '.join(sorted(missing))}."
    unknown = data.keys() - allowed
    if unknown:
        return None, f"Unknown field(s): {', '.join(sorted(unknown))}."

    cleaned: dict[str, Any] = {}
    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return None, "name must be a non-empty string."
        cleaned["name"] = data["name"].strip()
    if "quantity" in data:
        if isinstance(data["quantity"], bool) or not isinstance(data["quantity"], int) or data["quantity"] < 0:
            return None, "quantity must be a non-negative integer."
        cleaned["quantity"] = data["quantity"]
    if "price" in data:
        if isinstance(data["price"], bool) or not isinstance(data["price"], (int, float)) or data["price"] < 0:
            return None, "price must be a non-negative number."
        cleaned["price"] = float(data["price"])
    for field in ("barcode", "description"):
        if field in data:
            value = data[field]
            if value is not None and not isinstance(value, str):
                return None, f"{field} must be a string or null."
            cleaned[field] = (value or "").strip()
    return cleaned, None


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Application factory; tests can provide a temporary database path."""
    app = Flask(__name__)
    default_db = Path(__file__).with_name("inventory.db")
    app.config.from_mapping(
        DATABASE=os.environ.get("INVENTORY_DATABASE", str(default_db)),
        OPENFOODFACTS_URL="https://world.openfoodfacts.org/api/v2",
        TESTING=False,
    )
    if test_config:
        app.config.update(test_config)

    from flask import g

    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/items")
    def list_items():
        rows = get_db().execute("SELECT * FROM items ORDER BY id").fetchall()
        return jsonify([item_to_dict(row) for row in rows])

    @app.post("/api/items")
    def add_item():
        data, error = validate_item(request.get_json(silent=True))
        if error:
            return jsonify({"error": error}), 400
        try:
            cursor = get_db().execute(
                "INSERT INTO items (name, quantity, price, barcode, description) VALUES (?, ?, ?, ?, ?)",
                (data["name"], data["quantity"], data["price"], data.get("barcode", ""), data.get("description", "")),
            )
            get_db().commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "An item with this barcode already exists."}), 409
        row = get_db().execute("SELECT * FROM items WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(item_to_dict(row)), 201

    @app.get("/api/items/<int:item_id>")
    def get_item(item_id: int):
        row = get_db().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return jsonify({"error": "Item not found."}), 404
        return jsonify(item_to_dict(row))

    @app.patch("/api/items/<int:item_id>")
    def update_item(item_id: int):
        data, error = validate_item(request.get_json(silent=True), partial=True)
        if error:
            return jsonify({"error": error}), 400
        if not data:
            return jsonify({"error": "Provide at least one field to update."}), 400
        db = get_db()
        if db.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone() is None:
            return jsonify({"error": "Item not found."}), 404
        assignments = ", ".join(f"{key} = ?" for key in data)
        try:
            db.execute(f"UPDATE items SET {assignments} WHERE id = ?", (*data.values(), item_id))
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "An item with this barcode already exists."}), 409
        row = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return jsonify(item_to_dict(row))

    @app.delete("/api/items/<int:item_id>")
    def delete_item(item_id: int):
        db = get_db()
        cursor = db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({"error": "Item not found."}), 404
        return jsonify({"message": "Item deleted."})

    @app.get("/api/products/lookup")
    def lookup_product():
        barcode = request.args.get("barcode", "").strip()
        name = request.args.get("name", "").strip()
        if not barcode and not name:
            return jsonify({"error": "Provide a barcode or name query parameter."}), 400
        try:
            if barcode:
                url = f"{current_app.config['OPENFOODFACTS_URL']}/product/{barcode}.json"
                response = requests.get(
                    url,
                    headers={"User-Agent": "InventoryManagementSystem/1.0"},
                    timeout=8,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") != 1:
                    return jsonify({"error": "Product not found in OpenFoodFacts."}), 404
                product = payload.get("product", {})
            else:
                response = requests.get(
                    f"{current_app.config['OPENFOODFACTS_URL']}/search",
                    params={"search_terms": name, "page_size": 1, "json": 1},
                    headers={"User-Agent": "InventoryManagementSystem/1.0"},
                    timeout=8,
                )
                response.raise_for_status()
                products = response.json().get("products", [])
                if not products:
                    return jsonify({"error": "Product not found in OpenFoodFacts."}), 404
                product = products[0]
        except (requests.RequestException, ValueError) as exc:
            return jsonify({"error": f"Product lookup failed: {exc}"}), 502
        return jsonify({
            "name": product.get("product_name", ""),
            "barcode": product.get("code", barcode),
            "brand": product.get("brands", ""),
            "description": product.get("generic_name", ""),
            "categories": product.get("categories", ""),
            "image_url": product.get("image_url", ""),
        })

    @app.post("/api/products/import")
    def import_product():
        """Look up a product, then add the lookup details to local inventory."""
        query = request.get_json(silent=True)
        if not isinstance(query, dict) or not (query.get("barcode") or query.get("name")):
            return jsonify({"error": "Provide a barcode or name in the JSON body."}), 400
        lookup_client = app.test_client()
        params = {key: query[key] for key in ("barcode", "name") if query.get(key)}
        lookup = lookup_client.get("/api/products/lookup", query_string=params)
        if lookup.status_code != 200:
            return lookup
        product = lookup.get_json()
        item_data = {
            "name": product["name"] or query.get("name") or "Unnamed product",
            "barcode": product["barcode"] or "",
            "description": product["description"] or product["categories"],
            "quantity": query.get("quantity", 1),
            "price": query.get("price", 0),
        }
        cleaned, error = validate_item(item_data)
        if error:
            return jsonify({"error": error}), 400
        try:
            db = get_db()
            cursor = db.execute(
                "INSERT INTO items (name, quantity, price, barcode, description) VALUES (?, ?, ?, ?, ?)",
                (cleaned["name"], cleaned["quantity"], cleaned["price"], cleaned.get("barcode", ""), cleaned.get("description", "")),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "An item with this barcode already exists."}), 409
        row = get_db().execute("SELECT * FROM items WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(item_to_dict(row)), 201

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
