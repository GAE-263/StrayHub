# FurKids demo dataset

## Purpose and entry point

This local-only dataset creates a tenant named `毛小孩幸福聯盟協會` from five
public animal profile pages and ingests their approved primary photos. Run it
after migrations with:

```bash
uv run python -m scripts.seed_furkids_demo
```

`scripts/demo.sh` also runs this module. The module uses stable UUIDv5 identifiers
and natural-key lookups, updates its own fixture rows in place, and is safe to run
repeatedly. It does not delete or alter the existing `ORG-A` / `ORG-B` fixtures.

## Organization and locations

- Organization: `毛小孩幸福聯盟協會`
- Code: `FURKIDS-ASIA`
- Status: `active`
- Timezone: `Asia/Taipei`
- Address, service area, and contact: null because they are not required and were
  not verified for this dataset.
- `大型犬區` (`area`) contains `M-01` through `M-04` (`cage`).
- `特殊照護區` (`area`) contains `S-01` (`cage`).

## Source-derived data

Only the facts in this section are derived from the linked public pages.
After migration `0036_animal_profile`, `ANIMAL_PROFILES` persists the supported
profile fields directly on `Animal`; they are not disguised as medical records,
care reports, shelter numbers, or area data. The source lower bounds are copied
as descriptions, not recalculated as the animal's exact current age.

| Animal | Public profile | Source-derived facts retained in manifest |
| --- | --- | --- |
| 獒黃妹 | [profile](https://furkidsasia.weebly.com/295224064322969-huang-mei) | Intake 2014-05-31; senior; friendly with people, gentle and affectionate; source describes a dog-interaction caution. |
| 獒一搓 | [profile](https://furkidsasia.weebly.com/295221996825619-yi-cuo) | Intake 2024-12-13; friendly and affectionate; not especially shy with people. The public page has contradictory bilingual sex wording; the approved project decision is 公犬. |
| 獒瓦蛤 | [profile](https://furkidsasia.weebly.com/295222992634532-ua-ha) | Intake 2024-05-15; friendly and playful; more cautious around other dogs; source describes digestive sensitivity. |
| 獒凱西 | [profile](https://furkidsasia.weebly.com/295222097735199-cash) | Intake 2020-06-05; friendly, playful, and social. |
| 柴福福 | [profile](https://furkidsasia.weebly.com/266123111931119-fu-fu) | Intake 2017-09-22; male; mixed Shiba type; source describes congenital blindness in both eyes; friendly and likes exploring. |

The shelter numbers are project decisions, not source identifiers:

| Animal | Shelter number | Cage | Persisted status |
| --- | --- | --- | --- |
| 獒黃妹 | `MTF-20140531-001` | `M-01` | active |
| 獒一搓 | `MTF-20241213-001` | `M-02` | active |
| 獒瓦蛤 | `MTF-20240515-001` | `M-03` | active |
| 獒凱西 | `MTF-20200605-001` | `M-04` | active |
| 柴福福 | `SBA-20170922-001` | `S-01` | active |

## Persisted profile provenance

Profile wording was checked against the linked source pages on 2026-08-26.
Every sex/breed/intake/age/behavior value below is **SOURCE-DERIVED**, except
一搓's sex is **PROJECT-DECIDED**: the source says `公犬 Female` and its narrative
describes a boy; the approved project decision is `male`. Behavior is a short
source-derived summary, not a direct quotation. The database uses constrained
`male` / `female` / `unknown` values.

| Animal | Sex | Breed | Intake date | Age description | Behavior |
| --- | --- | --- | --- | --- | --- |
| 獒黃妹 | female | 獒犬 | 2014-05-31 | 10歲以上 | 親人、溫柔且喜歡撒嬌；與其他犬隻互動時需特別留意。 |
| 獒一搓 | male (PROJECT-DECIDED) | 藏獒 | 2024-12-13 | 5歲以上 | 親人、愛撒嬌；初次見面也願意主動靠近人。 |
| 獒瓦蛤 | female | 藏獒 | 2024-05-15 | 5歲以上 | 親人、愛玩；面對其他犬隻較謹慎，在陌生環境喜歡跟著熟悉的人。 |
| 獒凱西 | female | 混種獒犬 | 2020-06-05 | 7歲以上 | 親人、愛玩且合群。 |
| 柴福福 | male | 混種柴犬 | 2017-09-22 | 5歲以上 | 喜歡探索環境，對人親近、愛撒嬌，也會主動與其他犬隻互動。 |

All five have `birth_date=null`, `birth_date_estimated=false` — a
**PROJECT-DECIDED representation of unknown dates**, not fabricated birthdays.
Names retain Chinese only; shelter numbers, area assignments and active status
remain **PROJECT-DECIDED** Demo values.

The following `care_guidance` is **SYNTHETIC OPERATIONAL GUIDANCE**, written for
the StrayHub demo using the source cautions as context. It is neither quoted
FurKids instruction nor a medical diagnosis/treatment recommendation:

| Animal | Guidance | Basis / absence |
| --- | --- | --- |
| 獒黃妹 | 與其他犬隻保持適當距離；互動與牽行請依現場人員安排。 | Source describes caution around dogs |
| 獒一搓 | null | PROJECT-DECIDED: no special immediate guidance justified |
| 獒瓦蛤 | 腸胃較敏感，飲食及零食請依現場安排。 | Source describes digestive sensitivity |
| 獒凱西 | null | PROJECT-DECIDED: no special immediate guidance justified |
| 柴福福 | 視覺障礙；接近或觸碰前先以聲音讓牠知道你的位置，並依現場安排引導動線。 | Source describes blindness |

`behavior_notes` is management-only. `care_guidance` is safe volunteer-visible
operational text. See [Animal profile V1](../design/animal-profile.md).

## Approved primary-photo provenance

The FurKids organization explicitly approved these original images for use in
the StrayHub project demo. This approval is limited to that demo use and is not
a claim that StrayHub owns the images or has a broader redistribution license.

| Animal | Source profile | Approved selected original | Stored object key | Ingestion |
| --- | --- | --- | --- | --- |
| 獒黃妹 | [profile](https://furkidsasia.weebly.com/295224064322969-huang-mei) | [primary photo](https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/1347663248_orig.jpg) | `furkids-demo/animals/MTF-20140531-001/primary.jpg` | processed; `current_photo_key` set |
| 獒一搓 | [profile](https://furkidsasia.weebly.com/295221996825619-yi-cuo) | [primary photo](https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/s-52420615-0_orig.jpg) | `furkids-demo/animals/MTF-20241213-001/primary.jpg` | processed; `current_photo_key` set |
| 獒瓦蛤 | [profile](https://furkidsasia.weebly.com/295222992634532-ua-ha) | [primary photo](https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/447692789-851850686969842-5265211632358069069-n_1.jpg) | `furkids-demo/animals/MTF-20240515-001/primary.jpg` | processed; `current_photo_key` set |
| 獒凱西 | [profile](https://furkidsasia.weebly.com/295222097735199-cash) | [primary photo](https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/editor/1620557754.jpg?1600933902) | `furkids-demo/animals/MTF-20200605-001/primary.jpg` | processed; `current_photo_key` set |
| 柴福福 | [profile](https://furkidsasia.weebly.com/266123111931119-fu-fu) | [primary photo](https://furkidsasia.weebly.com/uploads/6/6/1/8/66183257/s-249888796_1.jpg) | `furkids-demo/animals/SBA-20170922-001/primary.jpg` | processed; `current_photo_key` set |

The five URLs are static trusted seed constants. The seed checks each approved
original's SHA-256 before processing, validates its declared and actual JPEG
format, re-encodes it through `MediaProcessingService` to remove metadata,
stores it through the tenant-scoped `MinioStorageAdapter`, and creates or reuses
a processed `MediaAsset` with purpose `animal_primary`. Remote URLs are never
stored in `Animal.current_photo_key`, and no generic URL-fetch API is exposed.

## StrayHub synthetic demo data

Everything in this section is fictional operational demo data, not a record from
the source organization:

- 8 medical records: one examination and one synthetic weight for 獒黃妹; one
  examination for 獒一搓; one visit and one synthetic weight for 獒瓦蛤; one
  examination for 獒凱西; one examination and one synthetic weight for 柴福福.
  Titles and content are marked `[合成示範]`; clinic and veterinarian are null.
- 3 active monthly reminder series at 09:00 Asia/Taipei: `高齡犬狀況追蹤`,
  `腸胃與體重狀況追蹤`, and `特殊照護狀況追蹤`.
- 20 saved care reports using supported answer codes and snapshots: 4 for 獒黃妹,
  3 for 獒一搓, 5 for 獒瓦蛤, 4 for 獒凱西, and 4 for 柴福福.
- Two fictional local accounts, one shelter-admin membership, one effective
  volunteer membership, one approved application, and one active matching grant.
  The usernames contain no real-person PII.

## QR-first and authorization behavior

Each animal has exactly one deterministic active `AnimalQrCode`. Its printable
token is signed by the existing `issue_printable_qr_token()` implementation and
is never printed by the seed. The manager profile can reconstruct and preview
the same token through the existing QR service.

The demo volunteer has an active, time-bounded `VOLUNTEER` membership and a
matching active `VolunteerAccessGrant`. No `DailyReportableScope` is created.
Ordinary QR-first resolution, animal confirmation, and care-report handoff rely
on the current effective membership/grant, verified organization, active animal,
and valid QR rules documented in
[`docs/design/care-report-handoff.md`](../design/care-report-handoff.md).
`DailyReportableScope` remains legacy/history and is not repurposed as a
restriction model.

## Idempotency contract

- Organization: lookup by unique code; stable ID on first creation.
- Areas and cages: lookup by organization/name/parent; stable IDs on creation.
- Animals: lookup by organization/shelter number; stable IDs and mappings.
- Profiles: validate `ANIMAL_PROFILES`, then update the same animals in place.
  Seed reruns restore this Demo profile manifest; do not use this seed on live
  shelter records. Existing photo checksums and QR bindings are preserved.
- QR: deterministic record ID; all other active QR rows for that animal are
  revoked so at most one remains active.
- Medical records, reminder series, and care reports: deterministic IDs and
  update-in-place behavior.
- Primary photos: deterministic object keys and `MediaAsset` IDs. A rerun reads
  the tenant-scoped stored object, verifies its bytes against the recorded
  processed checksum and metadata state, and skips the remote download when it
  is valid. Missing or invalid objects are downloaded only from the five static
  approved URLs, source-checksummed, sanitized, and overwritten at the same key.
- Users, memberships, application, and grant: stable identity plus natural-key
  lookup; no daily reportable scope is created.

The seed intentionally performs no schema migration. Run Alembic upgrade before
seeding; the profile fields require `0036_animal_profile`.
