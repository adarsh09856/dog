"""Validate captured answers before storing a workspace form submission."""

import math
import re
import uuid

from api.db import forms as form_db


def validate_answers(fields, data):
    answers = dict(data)
    for field in fields:
        key = field.get("name") or field.get("id") or field.get("label")
        if not key:
            continue
        value = answers.get(key)
        if isinstance(value, str):
            value = value.strip()
            answers[key] = value
        if value is None or value == "" or value == []:
            if field.get("required"):
                raise ValueError(f"{field.get('label') or key} is required")
            continue
        kind = field.get("type", "text")
        if kind == "number":
            if isinstance(value, int) and not isinstance(value, bool):
                continue
            if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
                answers[key] = int(value)
                continue
            try:
                if isinstance(value, bool):
                    raise TypeError
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{key} must be a number") from exc
            answers[key] = int(number) if number.is_integer() else number
        elif kind == "checkbox":
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
        elif not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        elif kind == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError(f"{key} must be a valid email address")
        elif kind == "phone" and (
            not 7 <= sum(character.isdigit() for character in value) <= 15
            or not re.fullmatch(r"\+?[\d() -]+", value)
        ):
            raise ValueError(f"{key} must be a valid phone number")
        elif (
            kind == "select" and field.get("options") and value not in field["options"]
        ):
            raise ValueError(f"{key} must be one of the configured options")
    return answers


async def submit_answers(
    organization_id, form_id, data, *, contact_id=None, call_id=None
):
    try:
        form_uuid = uuid.UUID(form_id)
    except ValueError as exc:
        raise ValueError("Invalid form ID") from exc
    try:
        contact_uuid = uuid.UUID(contact_id) if contact_id else None
    except ValueError as exc:
        raise ValueError("Invalid contact ID") from exc
    form = await form_db.get_form(organization_id, form_uuid)
    if form is None:
        raise LookupError("Form not found")
    if not form.is_active:
        raise ValueError("This form is disabled")
    fields = form.fields_schema or []
    answers = validate_answers(fields, data)
    return await form_db.create_submission(
        organization_id,
        form_uuid,
        answers,
        contact_id=contact_uuid,
        call_id=call_id,
        expected_fields=fields,
    )
