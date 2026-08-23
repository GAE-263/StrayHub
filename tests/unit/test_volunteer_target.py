from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.volunteer_target import (
    EntryTarget,
    OrganizationTarget,
    build_volunteer_target,
)

VALID_REFERENCE = "opaque-entry-reference-0123456789abcdef"


def test_organization_id_only_builds_organization_target() -> None:
    organization_id = uuid4()

    target = build_volunteer_target(organization_id=organization_id)

    assert isinstance(target, OrganizationTarget)
    assert target.organization_id == organization_id


def test_shelter_entry_reference_only_builds_entry_target() -> None:
    reference = VALID_REFERENCE

    target = build_volunteer_target(shelter_entry_reference=reference)

    assert isinstance(target, EntryTarget)
    assert target.shelter_entry_reference == reference


def test_missing_target_raises_target_required() -> None:
    with pytest.raises(DomainError) as exc_info:
        build_volunteer_target()

    assert exc_info.value.code == "target_required"
    assert exc_info.value.status_code == 422


def test_both_targets_raise_target_ambiguous() -> None:
    with pytest.raises(DomainError) as exc_info:
        build_volunteer_target(
            organization_id=uuid4(),
            shelter_entry_reference=VALID_REFERENCE,
        )

    assert exc_info.value.code == "target_ambiguous"
    assert exc_info.value.status_code == 422


def test_organization_target_rejects_non_uuid_runtime_value() -> None:
    with pytest.raises(DomainError) as exc_info:
        OrganizationTarget(organization_id=str(uuid4()))  # type: ignore[arg-type]

    assert exc_info.value.code == "invalid_target"
    assert exc_info.value.status_code == 422


@pytest.mark.parametrize(
    "reference",
    (
        " " * 32,
        "a" * 31,
        "a" * 513,
        "a" * 31 + "/",
        "a" * 31 + "#",
        "a" * 16 + " " + "a" * 15,
    ),
)
def test_entry_target_rejects_invalid_runtime_reference(reference: str) -> None:
    with pytest.raises(DomainError) as exc_info:
        EntryTarget(shelter_entry_reference=reference)

    assert exc_info.value.code == "invalid_target"
    assert exc_info.value.status_code == 422


def test_entry_target_rejects_surrounding_whitespace() -> None:
    with pytest.raises(DomainError) as exc_info:
        EntryTarget(shelter_entry_reference=f"  {VALID_REFERENCE}  ")

    assert exc_info.value.code == "invalid_target"
    assert exc_info.value.status_code == 422


def test_entry_target_repr_and_str_redact_raw_reference() -> None:
    raw_reference = VALID_REFERENCE + "-secret"
    target = EntryTarget(shelter_entry_reference=raw_reference)

    assert raw_reference not in repr(target)
    assert raw_reference not in str(target)


def test_targets_are_frozen_against_assignment() -> None:
    organization_target = OrganizationTarget(organization_id=uuid4())
    entry_target = EntryTarget(shelter_entry_reference=VALID_REFERENCE)

    with pytest.raises(FrozenInstanceError):
        organization_target.organization_id = uuid4()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry_target.shelter_entry_reference = VALID_REFERENCE + "-changed"  # type: ignore[misc]
