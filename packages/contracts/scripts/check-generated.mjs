import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const directory = mkdtempSync(join(tmpdir(), "strayhub-contracts-"));
const generated = join(directory, "openapi.ts");
try {
  const result = spawnSync(
    "npx",
    [
      "openapi-typescript",
      "../../specs/001-volunteer-care-report/contracts/openapi.yaml",
      "-o",
      generated,
    ],
    { stdio: "inherit" },
  );
  if (result.status !== 0) process.exit(result.status ?? 1);

  const expected = readFileSync(generated, "utf8");
  const current = readFileSync("src/openapi.ts", "utf8");
  if (expected !== current) {
    console.error("Generated contract types are stale; run npm run generate.");
    process.exit(1);
  }

  const volunteerOperations = [
    "resolveVolunteerApplicationStatus",
    "submitVolunteerApplication",
    "withdrawVolunteerApplication",
    "getVolunteerAccessPolicy",
    "updateVolunteerAccessPolicy",
    "listVolunteerApplications",
    "createVolunteerDecisionBatch",
    "getVolunteerDecisionBatch",
    "listVolunteerDecisionBatchItems",
    "listVolunteerAccessGrants",
    "updateVolunteerAccessGrant",
    "listVolunteerNotificationFailures",
    "retryVolunteerNotifications",
  ];
  const volunteerSchemas = [
    "ApplicationStatus",
    "EffectiveAccessStatus",
    "GrantStatus",
    "BatchStatus",
    "BatchItemResult",
    "NotificationStatus",
    "NotificationEventType",
    "ErrorResponse",
    "VolunteerIdentityRequest",
    "VolunteerApplicationCreateRequest",
    "VolunteerApplicationWithdrawRequest",
    "VolunteerApplicationStatusResponse",
    "PublicOrganization",
    "VolunteerApplication",
    "VolunteerApplicationListResponse",
    "VolunteerApplicationServiceDate",
    "VolunteerApplicationDetailResponse",
    "VolunteerPiiRevealRequest",
    "VolunteerPiiRevealResponse",
    "VolunteerAccessPolicy",
    "VolunteerAccessPolicyUpdateRequest",
    "VolunteerDecisionBatchRequest",
    "ExplicitVolunteerDecisionSelection",
    "AllFilteredVolunteerDecisionSelection",
    "VolunteerApplicationBatchFilter",
    "VolunteerDecisionItemRequest",
    "VolunteerDecisionBatchResponse",
    "VolunteerDecisionBatchItemListResponse",
    "VolunteerDecisionItemResponse",
    "VolunteerAccessGrantSummary",
    "VolunteerAccessGrant",
    "VolunteerAccessGrantListResponse",
    "GrantPeriodUpdateRequest",
    "GrantRevokeRequest",
    "VolunteerNotification",
    "VolunteerNotificationListResponse",
    "VolunteerNotificationRetryRequest",
    "VolunteerNotificationRetryResponse",
    "VolunteerNotificationRetryItem",
  ];

  for (const operation of volunteerOperations) {
    if (!current.includes(`    ${operation}: {`)) {
      console.error(`Generated contract is missing volunteer operation: ${operation}`);
      process.exit(1);
    }
  }
  for (const schema of volunteerSchemas) {
    if (!current.includes(`        ${schema}:`)) {
      console.error(`Generated contract is missing volunteer schema: ${schema}`);
      process.exit(1);
    }
  }
} finally {
  rmSync(directory, { recursive: true, force: true });
}
