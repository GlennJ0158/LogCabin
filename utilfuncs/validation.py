"""Input validation. Every message names the field that caused the problem."""


class ValidationError(ValueError):
    """Raised when a field value is invalid; message includes the field name."""

    def __init__(self, field, message):
        self.field = field
        super().__init__(f"{field}: {message}")


def validate_number(field, value, minimum=None, maximum=None, decimals=None, required=True):
    """Validate numeric input (data type, min, max); return float rounded to decimals."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationError(field, "a value is required")
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValidationError(field, f"'{value}' is not a number")
    if num != num or num in (float("inf"), float("-inf")):
        raise ValidationError(field, f"'{value}' is not a finite number")
    if minimum is not None and num < minimum:
        raise ValidationError(field, f"{num} is less than the minimum {minimum}")
    if maximum is not None and num > maximum:
        raise ValidationError(field, f"{num} is greater than the maximum {maximum}")
    return round(num, decimals) if decimals is not None else num


def validate_text(field, value, min_len=0, max_len=None, required=True):
    """Validate text input (data type and length)."""
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValidationError(field, f"'{value}' is not text")
    value = value.strip()
    if not value and required:
        raise ValidationError(field, "a value is required")
    if len(value) < min_len:
        raise ValidationError(field, f"length {len(value)} is below the minimum {min_len}")
    if max_len is not None and len(value) > max_len:
        raise ValidationError(field, f"length {len(value)} exceeds the maximum {max_len}")
    return value


def validate_bool(field, value):
    """Validate a binary field; accepts 1/0/True/False/'1'/'0'."""
    if value in (True, 1, "1"):
        return 1
    if value in (False, 0, "0"):
        return 0
    raise ValidationError(field, f"'{value}' is not a binary value (1 or 0)")


def validate_choice(field, value, allowed):
    """Validate that value is one of the allowed list items."""
    if value not in allowed:
        raise ValidationError(field, f"'{value}' is not one of {list(allowed)}")
    return value


def validate_bindings(form_name, bindings, variables):
    """Startup check: each control name must map to an existing variable.

    bindings: {control_name: variable_name}; variables: iterable of variable names.
    Raises ValidationError naming the first unbound control.
    """
    names = set(variables)
    for control, var in bindings.items():
        if var not in names:
            raise ValidationError(f"{form_name}.{control}", f"not connected to a variable (expected '{var}')")
