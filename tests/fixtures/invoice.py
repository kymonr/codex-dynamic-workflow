"""Deliberately incorrect, side-effect-free fixture for native raw-source review."""
def amount_due(subtotal: int, discount: int) -> int:
    """A discount reduces the subtotal; 100 with a discount of 10 should be 90."""
    return subtotal + discount
