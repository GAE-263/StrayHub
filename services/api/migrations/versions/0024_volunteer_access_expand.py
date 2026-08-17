"""Expand schema for volunteer applications and finite access."""

from alembic import op

revision = "0024_volunteer_access_expand"
down_revision = "0023_obs_vocab_management"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "organization_volunteer_access_policies",
    "shelter_volunteer_entry_references",
    "volunteer_applications",
    "volunteer_access_grants",
    "volunteer_decision_batches",
    "volunteer_decision_batch_items",
    "volunteer_notification_deliveries",
    "volunteer_notification_retry_batches",
    "volunteer_notification_retry_batch_items",
)


def _enable_tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {table}_tenant_scope ON {table}
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )


def upgrade() -> None:
    op.execute("ALTER TABLE organization_memberships ADD COLUMN valid_from timestamptz NULL")
    op.execute("ALTER TABLE organization_memberships ADD COLUMN expires_at timestamptz NULL")
    op.execute(
        "ALTER TABLE organization_memberships ADD COLUMN access_version integer NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE audit_records ADD COLUMN actor_type varchar(20) NULL")
    op.execute("ALTER TABLE audit_records ADD COLUMN actor_reference varchar(80) NULL")

    op.execute(
        """CREATE TABLE organization_volunteer_access_policies (
          organization_id uuid PRIMARY KEY REFERENCES organizations(id),
          applications_enabled boolean NOT NULL DEFAULT true,
          default_grant_duration_hours integer NOT NULL DEFAULT 168,
          version integer NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_volunteer_access_policy_positive_duration
            CHECK (default_grant_duration_hours > 0)
        )"""
    )
    op.execute(
        """INSERT INTO organization_volunteer_access_policies
          (organization_id, applications_enabled, default_grant_duration_hours,
           version, created_at, updated_at)
        SELECT id, true, 168, 1, now(), now()
        FROM organizations
        ON CONFLICT (organization_id) DO NOTHING"""
    )

    op.execute(
        """CREATE TABLE shelter_volunteer_entry_references (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          token_digest varchar(64) NOT NULL UNIQUE,
          purpose varchar(80) NOT NULL DEFAULT 'volunteer_application_entry',
          status varchar(20) NOT NULL DEFAULT 'active',
          issued_by_user_id uuid NULL REFERENCES users(id),
          issued_by_actor_reference varchar(80) NULL,
          issued_at timestamptz NOT NULL DEFAULT now(),
          revoked_by_user_id uuid NULL REFERENCES users(id),
          revoked_by_actor_reference varchar(80) NULL,
          revoked_at timestamptz NULL,
          rotation_group_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_volunteer_entry_reference_status
            CHECK (status IN ('active', 'revoked')),
          CONSTRAINT ck_volunteer_entry_reference_issue_actor CHECK (
            (issued_by_user_id IS NOT NULL) <> (issued_by_actor_reference IS NOT NULL)
          ),
          CONSTRAINT ck_volunteer_entry_reference_revoke_fields CHECK (
            (status = 'active' AND revoked_at IS NULL
              AND revoked_by_user_id IS NULL AND revoked_by_actor_reference IS NULL)
            OR
            (status = 'revoked' AND revoked_at IS NOT NULL AND
              ((revoked_by_user_id IS NOT NULL) <>
               (revoked_by_actor_reference IS NOT NULL)))
          )
        )"""
    )
    op.execute(
        "CREATE INDEX ix_volunteer_entry_reference_org_status_issued "
        "ON shelter_volunteer_entry_references "
        "(organization_id, status, issued_at DESC)"
    )

    op.execute(
        """CREATE TABLE volunteer_applications (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          user_id uuid NOT NULL REFERENCES users(id),
          status varchar(20) NOT NULL DEFAULT 'pending',
          source_channel varchar(30) NOT NULL DEFAULT 'liff',
          client_request_id uuid NULL,
          previous_application_id uuid NULL REFERENCES volunteer_applications(id),
          submitted_at timestamptz NOT NULL DEFAULT now(),
          decided_at timestamptz NULL,
          decided_by_user_id uuid NULL REFERENCES users(id),
          decision_reason varchar(500) NULL,
          withdrawn_at timestamptz NULL,
          version integer NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_volunteer_applications_status CHECK (
            status IN ('pending', 'approved', 'rejected', 'withdrawn')
          ),
          CONSTRAINT ck_volunteer_applications_terminal_fields CHECK (
            (status NOT IN ('approved', 'rejected') OR decided_at IS NOT NULL)
            AND (status <> 'rejected' OR
              (decision_reason IS NOT NULL AND length(trim(decision_reason)) > 0))
            AND (status <> 'withdrawn' OR withdrawn_at IS NOT NULL)
          )
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_volunteer_applications_pending_user_org "
        "ON volunteer_applications (organization_id, user_id) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_volunteer_applications_client_request "
        "ON volunteer_applications (organization_id, user_id, client_request_id) "
        "WHERE client_request_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_volunteer_applications_org_status_submitted "
        "ON volunteer_applications (organization_id, status, submitted_at DESC, id)"
    )

    op.execute(
        """CREATE TABLE volunteer_access_grants (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          user_id uuid NOT NULL REFERENCES users(id),
          membership_id uuid NOT NULL REFERENCES organization_memberships(id),
          application_id uuid NOT NULL UNIQUE REFERENCES volunteer_applications(id),
          status varchar(20) NOT NULL DEFAULT 'active',
          valid_from timestamptz NOT NULL,
          expires_at timestamptz NOT NULL,
          approved_at timestamptz NOT NULL DEFAULT now(),
          approved_by_user_id uuid NULL REFERENCES users(id),
          policy_version_used integer NULL,
          duration_hours_used integer NULL,
          source_type varchar(30) NOT NULL DEFAULT 'manager_approval',
          revoked_at timestamptz NULL,
          revoked_by_user_id uuid NULL REFERENCES users(id),
          revocation_reason varchar(500) NULL,
          version integer NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_volunteer_access_grants_period CHECK (expires_at > valid_from),
          CONSTRAINT ck_volunteer_access_grants_status
            CHECK (status IN ('active', 'expired', 'revoked')),
          CONSTRAINT ck_volunteer_access_grants_revocation_fields CHECK (
            status <> 'revoked' OR
            (revoked_at IS NOT NULL AND revoked_by_user_id IS NOT NULL
             AND revocation_reason IS NOT NULL
             AND length(trim(revocation_reason)) > 0)
          )
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_volunteer_access_grants_active_membership "
        "ON volunteer_access_grants (membership_id) WHERE status = 'active'"
    )
    op.execute(
        "CREATE INDEX ix_volunteer_access_grants_due ON volunteer_access_grants "
        "(status, expires_at, organization_id) WHERE status = 'active'"
    )

    op.execute(
        """CREATE TABLE volunteer_decision_batches (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          operation_id uuid NOT NULL,
          actor_user_id uuid NOT NULL REFERENCES users(id),
          platform_support_reason varchar(500) NULL,
          decision varchar(20) NOT NULL,
          reason varchar(500) NULL,
          default_valid_from timestamptz NULL,
          default_expires_at timestamptz NULL,
          policy_version_used integer NULL,
          default_duration_hours_used integer NULL,
          selection_mode varchar(30) NOT NULL,
          filter_snapshot jsonb NULL,
          snapshot_at timestamptz NOT NULL DEFAULT now(),
          request_fingerprint varchar(64) NOT NULL,
          status varchar(30) NOT NULL DEFAULT 'queued',
          requested_count integer NOT NULL,
          processed_count integer NOT NULL DEFAULT 0,
          succeeded_count integer NOT NULL DEFAULT 0,
          conflict_count integer NOT NULL DEFAULT 0,
          failed_count integer NOT NULL DEFAULT 0,
          completed_at timestamptz NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_volunteer_decision_batches_operation
            UNIQUE (organization_id, operation_id),
          CONSTRAINT ck_volunteer_decision_batches_requested CHECK (requested_count > 0),
          CONSTRAINT ck_volunteer_decision_batches_counts CHECK (
            processed_count = succeeded_count + conflict_count + failed_count
          )
        )"""
    )

    op.execute(
        """CREATE TABLE volunteer_decision_batch_items (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          batch_id uuid NOT NULL REFERENCES volunteer_decision_batches(id),
          application_id uuid NOT NULL REFERENCES volunteer_applications(id),
          expected_version integer NOT NULL,
          override_valid_from timestamptz NULL,
          override_expires_at timestamptz NULL,
          result varchar(20) NOT NULL DEFAULT 'pending',
          claim_token uuid NULL,
          claimed_at timestamptz NULL,
          claimed_by varchar(120) NULL,
          error_code varchar(100) NULL,
          resulting_application_version integer NULL,
          membership_id uuid NULL REFERENCES organization_memberships(id),
          grant_id uuid NULL REFERENCES volunteer_access_grants(id),
          processed_at timestamptz NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_volunteer_decision_batch_items_target
            UNIQUE (batch_id, application_id)
        )"""
    )
    op.execute(
        "CREATE INDEX ix_volunteer_decision_batch_items_claim "
        "ON volunteer_decision_batch_items (organization_id, batch_id, result, id)"
    )

    op.execute(
        """CREATE TABLE volunteer_notification_deliveries (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          user_id uuid NOT NULL REFERENCES users(id),
          line_binding_id uuid NULL REFERENCES line_user_bindings(id),
          event_type varchar(50) NOT NULL,
          resource_type varchar(50) NOT NULL,
          resource_id uuid NOT NULL,
          idempotency_key varchar(160) NOT NULL,
          payload jsonb NOT NULL,
          status varchar(20) NOT NULL DEFAULT 'pending',
          attempt_count integer NOT NULL DEFAULT 0,
          available_at timestamptz NOT NULL DEFAULT now(),
          claim_token uuid NULL,
          claimed_at timestamptz NULL,
          claimed_by varchar(120) NULL,
          last_error_code varchar(100) NULL,
          last_failed_at timestamptz NULL,
          sent_at timestamptz NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_volunteer_notifications_event
            UNIQUE (organization_id, idempotency_key),
          CONSTRAINT ck_volunteer_notifications_attempt_count CHECK (attempt_count >= 0)
        )"""
    )
    op.execute(
        "CREATE INDEX ix_volunteer_notifications_claim ON volunteer_notification_deliveries "
        "(status, available_at, organization_id)"
    )
    op.execute(
        "CREATE INDEX ix_volunteer_notifications_failure_list "
        "ON volunteer_notification_deliveries "
        "(organization_id, status, last_failed_at DESC, id) "
        "WHERE status IN ('retry_wait', 'failed')"
    )

    op.execute(
        """CREATE TABLE volunteer_notification_retry_batches (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          operation_id uuid NOT NULL,
          actor_user_id uuid NOT NULL REFERENCES users(id),
          platform_support_reason varchar(500) NULL,
          request_fingerprint varchar(64) NOT NULL,
          requested_count integer NOT NULL,
          requeued_count integer NOT NULL DEFAULT 0,
          conflict_count integer NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_volunteer_notification_retry_batches_operation
            UNIQUE (organization_id, operation_id)
        )"""
    )
    op.execute(
        """CREATE TABLE volunteer_notification_retry_batch_items (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          batch_id uuid NOT NULL REFERENCES volunteer_notification_retry_batches(id),
          notification_delivery_id uuid NOT NULL REFERENCES volunteer_notification_deliveries(id),
          result varchar(20) NOT NULL,
          error_code varchar(100) NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_volunteer_notification_retry_items_target
            UNIQUE (batch_id, notification_delivery_id)
        )"""
    )

    op.execute(
        "CREATE INDEX ix_org_memberships_volunteer_due ON organization_memberships "
        "(organization_id, status, expires_at) "
        "WHERE role = 'VOLUNTEER' AND status = 'active'"
    )
    op.execute(
        "CREATE INDEX ix_audit_records_org_actor_reference_created ON audit_records "
        "(organization_id, actor_type, actor_reference, created_at DESC)"
    )

    for table in TENANT_TABLES:
        _enable_tenant_rls(table)
        if table != "shelter_volunteer_entry_references":
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO strayhub_runtime")

    op.execute(
        """CREATE OR REPLACE FUNCTION resolve_volunteer_entry_reference(
          p_token_digest text,
          p_purpose text DEFAULT 'volunteer_application_entry'
        ) RETURNS TABLE(reference_id uuid, organization_id uuid)
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public, pg_temp
        AS $$
          SELECT entry.id, entry.organization_id
          FROM shelter_volunteer_entry_references AS entry
          JOIN organizations AS organization ON organization.id = entry.organization_id
          WHERE entry.token_digest = p_token_digest
            AND entry.purpose = p_purpose
            AND entry.status = 'active'
            AND organization.status = 'active'
          LIMIT 1
        $$"""
    )
    op.execute("REVOKE ALL ON FUNCTION resolve_volunteer_entry_reference(text, text) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION resolve_volunteer_entry_reference(text, text) "
        "TO strayhub_runtime"
    )
    op.execute("REVOKE ALL ON shelter_volunteer_entry_references FROM strayhub_runtime")


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON FUNCTION resolve_volunteer_entry_reference(text, text) FROM strayhub_runtime"
    )
    op.execute("DROP FUNCTION IF EXISTS resolve_volunteer_entry_reference(text, text)")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
        op.execute(f"DROP TABLE {table} CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_audit_records_org_actor_reference_created")
    op.execute("DROP INDEX IF EXISTS ix_org_memberships_volunteer_due")
    op.execute("ALTER TABLE audit_records DROP COLUMN actor_reference")
    op.execute("ALTER TABLE audit_records DROP COLUMN actor_type")
    op.execute("ALTER TABLE organization_memberships DROP COLUMN access_version")
    op.execute("ALTER TABLE organization_memberships DROP COLUMN expires_at")
    op.execute("ALTER TABLE organization_memberships DROP COLUMN valid_from")
