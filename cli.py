"""Command-line client for the inventory REST API."""

import argparse
import json
import sys

import requests


def print_response(response: requests.Response) -> int:
    """Print JSON responses clearly and return a shell exit code."""
    try:
        body = response.json()
    except ValueError:
        body = response.text
    print(json.dumps(body, indent=2))
    if not response.ok:
        print(f"HTTP {response.status_code}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage inventory through the Flask API.")
    parser.add_argument("--url", default="http://127.0.0.1:5000", help="API base URL")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List all inventory items")
    get_cmd = commands.add_parser("get", help="Get one item")
    get_cmd.add_argument("id", type=int)
    add_cmd = commands.add_parser("add", help="Add an item")
    add_cmd.add_argument("--name", required=True)
    add_cmd.add_argument("--quantity", required=True, type=int)
    add_cmd.add_argument("--price", required=True, type=float)
    add_cmd.add_argument("--barcode", default="")
    add_cmd.add_argument("--description", default="")
    update_cmd = commands.add_parser("update", help="Partially update an item")
    update_cmd.add_argument("id", type=int)
    update_cmd.add_argument("--name")
    update_cmd.add_argument("--quantity", type=int)
    update_cmd.add_argument("--price", type=float)
    update_cmd.add_argument("--barcode")
    update_cmd.add_argument("--description")
    delete_cmd = commands.add_parser("delete", help="Delete an item")
    delete_cmd.add_argument("id", type=int)
    lookup_cmd = commands.add_parser("lookup", help="Search OpenFoodFacts")
    lookup_group = lookup_cmd.add_mutually_exclusive_group(required=True)
    lookup_group.add_argument("--barcode")
    lookup_group.add_argument("--name")
    import_cmd = commands.add_parser("import-product", help="Look up a product and add it to inventory")
    import_group = import_cmd.add_mutually_exclusive_group(required=True)
    import_group.add_argument("--barcode")
    import_group.add_argument("--name")
    import_cmd.add_argument("--quantity", type=int, default=1)
    import_cmd.add_argument("--price", type=float, default=0)

    args = parser.parse_args()
    base = args.url.rstrip("/")
    try:
        if args.command == "list":
            response = requests.get(f"{base}/api/items", timeout=8)
        elif args.command == "get":
            response = requests.get(f"{base}/api/items/{args.id}", timeout=8)
        elif args.command == "add":
            body = {key: getattr(args, key) for key in ("name", "quantity", "price", "barcode", "description")}
            response = requests.post(f"{base}/api/items", json=body, timeout=8)
        elif args.command == "update":
            body = {key: getattr(args, key) for key in ("name", "quantity", "price", "barcode", "description") if getattr(args, key) is not None}
            response = requests.patch(f"{base}/api/items/{args.id}", json=body, timeout=8)
        elif args.command == "delete":
            response = requests.delete(f"{base}/api/items/{args.id}", timeout=8)
        elif args.command == "lookup":
            query = {"barcode": args.barcode} if args.barcode else {"name": args.name}
            response = requests.get(f"{base}/api/products/lookup", params=query, timeout=12)
        else:
            body = {"barcode": args.barcode, "quantity": args.quantity, "price": args.price} if args.barcode else {"name": args.name, "quantity": args.quantity, "price": args.price}
            response = requests.post(f"{base}/api/products/import", json=body, timeout=15)
        return print_response(response)
    except requests.RequestException as exc:
        print(f"Could not reach the API: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
