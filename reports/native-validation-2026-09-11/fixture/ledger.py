def available_slots(capacity, active, reserved):
    """active counts running threads; reserved counts additional unstarted slots."""
    if min(capacity, active, reserved) < 0:
        raise ValueError("counts must be nonnegative")
    return max(0, capacity - max(active, reserved))


def can_deliver(mainline_complete, untriaged_risks):
    """Unfinished optional probes alone are not a delivery barrier."""
    return bool(mainline_complete) and not untriaged_risks
