"""Conservative MOA mapping, independent of database, clocks and shelter names."""

import json
import re
from dataclasses import dataclass
from datetime import date

SOURCE = "MOA_ADOPTION_OPEN_DATA"
SNAPSHOT_FIELDS = (
    "animal_id",
    "animal_subid",
    "animal_shelter_pkid",
    "animal_kind",
    "animal_Variety",
    "animal_sex",
    "animal_age",
    "animal_bodytype",
    "animal_colour",
    "animal_foundplace",
    "animal_sterilization",
    "animal_bacterin",
    "animal_remark",
    "animal_caption",
    "animal_opendate",
    "animal_closeddate",
    "animal_update",
    "animal_createtime",
    "animal_status",
    "shelter_name",
    "shelter_address",
    "shelter_tel",
    "album_file",
)


def clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def official_id(value: object) -> str:
    value = clean(value)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ValueError("invalid_official_id")
    return value


@dataclass(frozen=True)
class MoaAnimal:
    external_id: str
    shelter_id: str
    fields: dict
    source_updated_at: date | None
    image_url: str | None
    snapshot: dict


@dataclass(frozen=True)
class MoaBatch:
    fetched_count: int
    eligible_count: int
    shelter_id: str
    selected: list[MoaAnimal]
    present_ids: set[str]
    errors: list[dict]


@dataclass(frozen=True)
class MoaNameObservation:
    raw_name: str | None = None
    normalized_name: str | None = None
    error_code: str | None = None


def normalize_official_name(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("name_invalid_value")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise ValueError("name_invalid_value") from None
    normalized = " ".join(value.split())
    if size > 1024 or len(normalized) > 200:
        raise ValueError("name_value_too_large")
    # The official Vue template displays --- for an empty value, not an animal name.
    return None if normalized in {"", "---"} else normalized


def parse_name_detail(payload: object, record: MoaAnimal) -> MoaNameObservation:
    try:
        if not isinstance(payload, dict) or payload.get("Success") is not True:
            raise ValueError
        rows = json.loads(payload["Message"])
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError
        row = rows[0]
        if (
            row.get("收容編號") != record.fields["shelter_number"]
            or row.get("公告收容所") != record.snapshot["shelter_name"]
        ):
            raise ValueError("name_identity_mismatch")
        raw = row["動物名"]
        normalized = normalize_official_name(raw)
        if "AnimalName" in row and normalize_official_name(row["AnimalName"]) != normalized:
            raise ValueError("name_alias_mismatch")
        return MoaNameObservation(raw or "", normalized)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        code = str(exc)
        if code not in {
            "name_identity_mismatch",
            "name_alias_mismatch",
            "name_invalid_value",
            "name_value_too_large",
        }:
            code = "name_invalid_response"
        raise ValueError(code) from None


def normalize(row: dict) -> MoaAnimal:
    external_id = official_id(row.get("animal_id"))
    shelter_id = official_id(row.get("animal_shelter_pkid"))
    subid = clean(row.get("animal_subid"))
    breed = clean(row.get("animal_Variety"))
    if len(subid) > 120 or len(breed) > 120:
        raise ValueError("profile_field_too_long")
    raw_date = clean(row.get("animal_update"))
    try:
        updated = date.fromisoformat(raw_date.replace("/", "-")) if raw_date else None
    except ValueError as exc:
        raise ValueError("invalid_source_update_date") from exc
    # 23 whitelisted fields, each <= 1 KiB UTF-8; stays below the 32 KiB DB bound.
    snapshot = {
        key: clean(row.get(key)).encode("utf-8")[:1024].decode("utf-8", errors="ignore")
        for key in SNAPSHOT_FIELDS
    }
    if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) > 32768:
        raise ValueError("source_snapshot_too_large")
    return MoaAnimal(
        external_id,
        shelter_id,
        {
            "name": subid or f"MOA-{external_id}",
            "shelter_number": subid or None,
            "breed": breed or None,
            "sex": {"M": "male", "公": "male", "F": "female", "母": "female"}.get(
                clean(row.get("animal_sex")).upper(), "unknown"
            ),
            "age_description": {"ADULT": "成犬", "CHILD": "幼犬"}.get(
                clean(row.get("animal_age")).upper()
            ),
        },
        updated,
        clean(row.get("album_file")) or None,
        snapshot,
    )


def select_records(rows: list, *, shelter: str, kind: str, limit: int) -> MoaBatch:
    if not shelter.strip() or len(shelter.strip()) > 200 or kind != "dog" or not 1 <= limit <= 60:
        raise ValueError("explicit_shelter_dog_and_limit_1_to_60_required")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("invalid_or_empty_dataset")
    eligible = [
        row
        for row in rows
        if clean(row.get("shelter_name")) == shelter.strip()
        and clean(row.get("animal_kind")) == "狗"
    ]
    if not eligible:
        # Empty/renamed shelter responses must not turn every source row unavailable.
        raise ValueError("target_shelter_has_no_dogs")
    shelter_ids = {official_id(row.get("animal_shelter_pkid")) for row in eligible}
    if len(shelter_ids) != 1:
        raise ValueError("ambiguous_shelter_identity")
    present, values, errors = set(), [], []
    for row in eligible:
        try:
            identifier = official_id(row.get("animal_id"))
            if identifier in present:
                raise ValueError("duplicate_external_identity")
            present.add(identifier)
        except ValueError:
            raise ValueError("invalid_or_duplicate_external_identity") from None
        try:
            values.append(normalize(row))
        except ValueError as exc:
            errors.append({"external_id": identifier, "stage": "normalization", "code": str(exc)})
    values.sort(key=lambda r: (r.source_updated_at or date.min, int(r.external_id)), reverse=True)
    return MoaBatch(len(rows), len(eligible), shelter_ids.pop(), values[:limit], present, errors)
