"""Recipients we must not email (calendar/SMTP) — avoids DNS failures for demo seed addresses."""


def is_placeholder_invite_email(addr: str) -> bool:
    s = (addr or "").strip().lower()
    return bool(s) and s.endswith("@example.com")


def partition_invite_recipients(addresses: list[str] | None) -> tuple[list[str], list[str]]:
    """
    Split into (deliverable, placeholder).

    Placeholder addresses (currently @example.com only) are listed for the UI / event text
    but never passed to Google Calendar sendUpdates or SMTP.
    Dedupes by lowercased address.
    """
    if not addresses:
        return [], []
    deliverable: list[str] = []
    placeholder: list[str] = []
    seen_d: set[str] = set()
    seen_p: set[str] = set()
    for raw in addresses:
        e = (raw or "").strip()
        if not e:
            continue
        low = e.lower()
        if is_placeholder_invite_email(e):
            if low not in seen_p:
                seen_p.add(low)
                placeholder.append(e)
        elif low not in seen_d:
            seen_d.add(low)
            deliverable.append(e)
    return deliverable, placeholder


def filter_deliverable_invite_recipients(addresses: list[str] | None) -> list[str]:
    deliverable, _ = partition_invite_recipients(addresses)
    return deliverable
