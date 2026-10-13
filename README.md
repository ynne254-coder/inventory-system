# Inventory Management API

A beginner-friendly Flask REST API and command-line client for managing retail inventory. It stores items in SQLite, supports full CRUD operations, and can look up or import product details from [OpenFoodFacts](https://world.openfoodfacts.org/).

## Requirements

- Python 3.10 or newer
- Internet access for OpenFoodFacts lookup/import commands

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

The server is at `http://127.0.0.1:5000`. SQLite creates `inventory.db` automatically. Set `INVENTORY_DATABASE` to use a different database path.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Check that the server is running |
| GET | `/api/items` | List all inventory items |
| POST | `/api/items` | Create an item |
| GET | `/api/items/<id>` | Read one item |
| PATCH | `/api/items/<id>` | Update one or more fields |
| DELETE | `/api/items/<id>` | Delete an item |
| GET | `/api/products/lookup?barcode=<code>` | Look up a barcode in OpenFoodFacts |
| GET | `/api/products/lookup?name=<text>` | Search OpenFoodFacts by name |
| POST | `/api/products/import` | Look up a product and save it to inventory |

Create body example:

```json
{
  "name": "Oat milk",
  "quantity": 12,
  "price": 3.49,
  "barcode": "1234567890123",
  "description": "Unsweetened"
}
```

For product import, send a barcode or name; `quantity` and `price` are optional (default to 1 and 0):

```json
{"barcode": "3017620422003", "quantity": 8, "price": 4.25}
```

## CLI examples

Keep the Flask server running in one terminal, then in another terminal:

```bash
python cli.py list
python cli.py add --name "Oat milk" --quantity 12 --price 3.49
python cli.py get 1
python cli.py update 1 --quantity 10
python cli.py lookup --barcode 3017620422003
python cli.py import-product --barcode 3017620422003 --quantity 8 --price 4.25
python cli.py delete 1
```

Use `python cli.py --url http://localhost:5000 list` to point the client at another server. Run `python cli.py --help` or `python cli.py add --help` for command details.

## Tests

```bash
python -m pytest -q
```

Tests use a temporary SQLite database and mock OpenFoodFacts, so they do not need live internet access.

## How the code is organized

- `app.py`: Flask app factory, database setup, request validation, HTTP routes, and external product lookup.
- `cli.py`: parses terminal commands, sends HTTP requests to the Flask API, and prints results.
- `tests/`: checks API behavior using Flask's built-in test client.

A request reaches a Flask route, the route validates input, reads/writes SQLite, and returns JSON. The CLI is a separate client of those same HTTP routes. OpenFoodFacts is contacted only by the lookup/import endpoints; the inventory API otherwise works offline.
