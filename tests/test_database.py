"""Tests for the database connection, models and CRUD layer."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.database.crud import (
    count_phones,
    get_spec_value,
    list_phones,
    resolve_phone,
    top_phones_by,
    upsert_phone,
)
from app.database.models import Phone, Specification


def test_connection_and_tables(session):
    assert count_phones(session) >= 0
    assert session.query(Phone).count() >= 0


def test_seed_inserted_three_phones(seeded, session):
    assert count_phones(session) == 3


def test_upsert_is_idempotent(seeded, session):
    data = dict(seeded["s23"].__dict__)
    data["slug"] = seeded["s23"].slug
    data["name"] = seeded["s23"].name
    # Re-upsert with the same slug should not create a duplicate.
    before = count_phones(session)
    from app.database.crud import upsert_phone

    spec_payload = [
        {"category": s.category, "key": s.key, "value": s.value}
        for s in seeded["s23"].specifications
    ]
    data["specs"] = spec_payload
    upsert_phone(session, data)
    assert count_phones(session) == before


def test_slug_unique_constraint(session):
    with pytest.raises(IntegrityError):
        session.add(Phone(name="Dup", slug="samsung_galaxy_s23-12082.php"))
        session.commit()
    session.rollback()


def test_resolve_phone_fuzzy(seeded, session):
    assert resolve_phone(session, "s23").name == "Samsung Galaxy S23"
    assert resolve_phone(session, "Galaxy S22").name == "Samsung Galaxy S22 5G"
    assert resolve_phone(session, "s23 ultra").name == "Samsung Galaxy S23 Ultra"
    assert resolve_phone(session, "nonexistent phone") is None


def test_top_phones_by_battery(seeded, session):
    top = top_phones_by(session, "battery_capacity_mah", limit=1)
    assert top[0].name == "Samsung Galaxy S23 Ultra"
    assert top[0].battery_capacity_mah == 5000


def test_get_spec_value(seeded, session):
    val = get_spec_value(session, seeded["s23"], "Battery", "Type")
    assert val == "Li-Ion 3900 mAh"
    assert get_spec_value(session, seeded["s23"], "Battery", "DoesNotExist") is None


def test_list_phones_sorted(seeded, session):
    names = [p.name for p in list_phones(session)]
    assert names == sorted(names)


def test_specifications_relationship(seeded):
    specs = seeded["s23"].specifications
    assert isinstance(specs, list)
    assert any(s.category == "Display" for s in specs)
    assert all(isinstance(s, Specification) for s in specs)
