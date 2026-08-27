from decimal import Decimal


def to_decimal(value) -> Decimal:
    """Numeric columns can come back as float depending on the DB backend
    (SQLite has no native DECIMAL storage) - always round-trip through
    str() rather than constructing Decimal directly from a float, which
    would otherwise reproduce binary floating-point artifacts.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
