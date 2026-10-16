"""
Simplified FMCSA hours-of-service so ETAs on long trips aren't fantasy.

- 30 minute break once 8 hours have been driven since the last break/rest
- 10 hour rest after 11 hours of driving

The 14-hour duty window and the 70-hour/8-day cap are ignored; with
no on-duty non-driving time in the model they rarely change the answer
for a single trip.
"""
HOUR = 3600
DRIVE_LIMIT = 11 * HOUR
BREAK_AFTER = 8 * HOUR
BREAK_LEN = 30 * 60
REST_LEN = 10 * HOUR


def elapsed_for_drive(drive_s, enabled=True):
    """Wall-clock seconds needed to accumulate `drive_s` seconds of driving."""
    if not enabled or drive_s <= 0:
        return max(drive_s, 0)

    full_shifts, remainder = divmod(drive_s, DRIVE_LIMIT)
    full_shifts = int(full_shifts)

    elapsed = drive_s
    # every completed 11h shift had a break at hour 8, and is followed by a
    # 10h rest unless the trip ends exactly at the end of the shift
    elapsed += full_shifts * BREAK_LEN
    rests = full_shifts if remainder > 0 else max(full_shifts - 1, 0)
    elapsed += rests * REST_LEN
    if remainder > BREAK_AFTER:
        elapsed += BREAK_LEN
    return elapsed


def stops_for_drive(drive_s, enabled=True):
    """Human-readable count of the stops added above, for the route summary."""
    if not enabled or drive_s <= 0:
        return {"breaks": 0, "rests": 0}
    full_shifts, remainder = divmod(drive_s, DRIVE_LIMIT)
    full_shifts = int(full_shifts)
    rests = full_shifts if remainder > 0 else max(full_shifts - 1, 0)
    breaks = full_shifts + (1 if remainder > BREAK_AFTER else 0)
    return {"breaks": breaks, "rests": rests}
