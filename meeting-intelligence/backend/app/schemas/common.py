from bson import ObjectId


def oid_str(oid: ObjectId | str | None) -> str | None:
    if oid is None:
        return None
    return str(oid)


def parse_oid(s: str) -> ObjectId:
    if not ObjectId.is_valid(s):
        raise ValueError("invalid id")
    return ObjectId(s)
