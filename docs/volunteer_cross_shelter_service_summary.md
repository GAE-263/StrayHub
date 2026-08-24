# Cross-Shelter Volunteer Service Summary

## Scope

The summary is an informational, bounded history of service evidence for the
volunteer resolved from the currently authorized application. The public
management entry point is always:

```text
current organization + current application
```

The API never accepts an arbitrary volunteer `user_id` as its subject.

## Data classification

| Field | Cross-shelter summary | Current shelter detail | PII reveal |
| --- | --- | --- | --- |
| organization name/code | allowed | allowed | unnecessary |
| service date | allowed | allowed | unnecessary |
| service status | allowed when backed by a submitted care report | allowed | unnecessary |
| bounded record count | allowed | allowed | unnecessary |
| application/grant authorization state | denied as history evidence | current shelter only | unnecessary |
| animal name | denied | existing authorization only | unnecessary |
| care-report body/answers | denied | existing authorization only | unnecessary |
| applicant name | denied | masked | Item 1 only |
| phone | denied | masked | Item 1 only |
| LINE identity/token | never | never | never |
| ciphertext/key material | never | never | never |

## Service-history semantics

The source of evidence is `care_reports.submitted_at` for the volunteer. A
report row is evidence that a service report was submitted; it is not treated
as proof of a completed shift. `record_count` counts submitted care-report
rows grouped by organization and submitted service date. Archived reports
remain historical evidence and are represented as `archived`; other submitted
reports are represented as `recorded`.

An approved application, active grant, inactive grant, revoked grant, or
membership status is not converted into completed service and does not erase
historical report evidence.

## Authorization and purpose

Only an active same-organization `SHELTER_ADMIN` may request the summary with
purpose `volunteer_service_history_review`. Platform scope is denied for this
feature because no product policy currently authorizes platform support to
read cross-shelter volunteer history. Inactive or suspended membership and
cross-organization application IDs fail closed with scoped not-found/denied
semantics. Summary access is audited with metadata only; returned history,
PII, report content, and identifiers are not written to the audit payload.

The summary read does not grant or imply PII reveal permission. Item 1's
`application_review` purpose remains independent.

## Persistence and RLS boundary

`VolunteerAccessRepository` remains organization-scoped. A dedicated
`VolunteerServiceSummaryRepository` performs one allowlisted aggregate query
over `care_reports` and `organizations` after the current application has
resolved the subject server-side. It uses the existing controlled
`set_platform_scope` primitive only for this read, restores the current
organization scope immediately afterward, and never exposes that scope as a
generic repository capability.

The query selects only organization provenance, submitted date, derived
status, and count. It does not join PII, LINE identity, animal, media, or
care-report answer content. The API authorization decision is made before the
cross-shelter read.

Pagination is bounded, deterministic, and uses an opaque HMAC-signed cursor
bound to the application and resolved subject. A cursor cannot be reused for
another application or subject.
