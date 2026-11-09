"""Small shared helpers (money math, idempotency canonicalization)."""
import hashlib
import json


def canonical_request_hash(restaurant_id: int, items: list[tuple[int, int]]) -> str:
    """SHA-256 of the canonicalized checkout payload (D34).

    `items` is [(menu_item_id, quantity), ...]. Quantities for the same menu
    item are summed and pairs sorted, so any field ordering / duplicate line
    in the client payload yields the same hash for the same *intent*.
    """
    quantities: dict[int, int] = {}
    for menu_item_id, quantity in items:
        quantities[menu_item_id] = quantities.get(menu_item_id, 0) + quantity
    payload = {
        "restaurant_id": restaurant_id,
        "items": sorted(quantities.items()),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
