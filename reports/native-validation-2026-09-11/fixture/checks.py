from ledger import available_slots, can_deliver
assert available_slots(4, 2, 0) == 2
assert can_deliver(True, [])
assert not can_deliver(True, ["unresolved"])
