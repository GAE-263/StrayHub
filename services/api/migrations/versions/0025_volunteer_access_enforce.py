"""Backfill finite legacy volunteer access and enforce invariants."""

from alembic import op

revision = "0025_volunteer_access_enforce"
down_revision = "0024_volunteer_access_expand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One database timestamp keeps Membership, Application, Grant and Audit aligned.
    op.execute(
        """CREATE TEMP TABLE volunteer_access_migration_clock AS
        SELECT clock_timestamp() AS migrated_at"""
    )
    op.execute(
        """UPDATE organization_memberships AS membership
        SET valid_from = migration.migrated_at,
            expires_at = migration.migrated_at
              + make_interval(hours => policy.default_grant_duration_hours),
            access_version = access_version + 1,
            updated_at = migration.migrated_at
        FROM organization_volunteer_access_policies AS policy,
             volunteer_access_migration_clock AS migration
        WHERE membership.organization_id = policy.organization_id
          AND membership.role = 'VOLUNTEER'
          AND membership.status = 'active'
          AND membership.expires_at IS NULL"""
    )
    op.execute(
        """INSERT INTO volunteer_applications (
          id, organization_id, user_id, status, source_channel, submitted_at,
          decided_at, version, created_at, updated_at
        )
        SELECT md5(membership.id::text || chr(58) || 'legacy_application')::uuid,
               membership.organization_id, membership.user_id, 'approved',
               'legacy_migration', migration.migrated_at, migration.migrated_at,
               1, migration.migrated_at, migration.migrated_at
        FROM organization_memberships AS membership
        CROSS JOIN volunteer_access_migration_clock AS migration
        WHERE membership.role = 'VOLUNTEER'
          AND membership.status = 'active'
          AND membership.valid_from = migration.migrated_at
          AND NOT EXISTS (
            SELECT 1 FROM volunteer_applications AS application
            WHERE application.id = md5(
              membership.id::text || chr(58) || 'legacy_application'
            )::uuid
          )"""
    )
    op.execute(
        """INSERT INTO volunteer_access_grants (
          id, organization_id, user_id, membership_id, application_id, status,
          valid_from, expires_at, approved_at, policy_version_used,
          duration_hours_used, source_type, version, created_at, updated_at
        )
        SELECT md5(membership.id::text || chr(58) || 'legacy_grant')::uuid,
               membership.organization_id, membership.user_id, membership.id,
               md5(membership.id::text || chr(58) || 'legacy_application')::uuid,
               'active', membership.valid_from, membership.expires_at,
               migration.migrated_at, policy.version,
               policy.default_grant_duration_hours, 'legacy_migration', 1,
               migration.migrated_at, migration.migrated_at
        FROM organization_memberships AS membership
        JOIN organization_volunteer_access_policies AS policy
          ON policy.organization_id = membership.organization_id
        CROSS JOIN volunteer_access_migration_clock AS migration
        WHERE membership.role = 'VOLUNTEER'
          AND membership.status = 'active'
          AND membership.valid_from = migration.migrated_at
          AND NOT EXISTS (
            SELECT 1 FROM volunteer_access_grants AS grant_record
            WHERE grant_record.membership_id = membership.id
              AND grant_record.status = 'active'
          )"""
    )
    op.execute(
        """UPDATE audit_records
        SET actor_type = CASE
              WHEN actor_user_id IS NULL THEN 'system' ELSE 'user' END,
            actor_reference = CASE
              WHEN actor_user_id IS NULL THEN 'SYSTEM_MIGRATION' ELSE NULL END
        WHERE actor_type IS NULL"""
    )
    op.execute(
        """INSERT INTO audit_records (
          id, organization_id, actor_user_id, actor_type, actor_reference,
          operation_id, action, resource_type, resource_id, source_channel,
          after_data, result, created_at
        )
        SELECT md5(membership.id::text || chr(58) || 'legacy_audit')::uuid,
               membership.organization_id, NULL, 'system', 'SYSTEM_MIGRATION',
               md5(membership.id::text || chr(58) || 'legacy_operation')::uuid,
               'volunteer_access.legacy_migrated', 'organization_membership',
               membership.id, 'migration',
               jsonb_build_object(
                 'valid_from', membership.valid_from,
                 'expires_at', membership.expires_at,
                 'source_type', 'legacy_migration'
               ),
               'success', migration.migrated_at
        FROM organization_memberships AS membership
        CROSS JOIN volunteer_access_migration_clock AS migration
        WHERE membership.role = 'VOLUNTEER'
          AND membership.status = 'active'
          AND membership.valid_from = migration.migrated_at
          AND NOT EXISTS (
            SELECT 1 FROM audit_records AS audit
            WHERE audit.id = md5(
              membership.id::text || chr(58) || 'legacy_audit'
            )::uuid
          )"""
    )

    op.execute(
        """DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM organization_memberships
            WHERE role = 'VOLUNTEER' AND status = 'active'
              AND (valid_from IS NULL OR expires_at IS NULL OR expires_at <= valid_from)
          ) THEN
            RAISE EXCEPTION 'active VOLUNTEER membership remains unbounded';
          END IF;
        END $$"""
    )
    op.execute("ALTER TABLE audit_records ALTER COLUMN actor_type SET NOT NULL")
    op.execute(
        """ALTER TABLE audit_records ADD CONSTRAINT ck_audit_records_actor_identity CHECK (
          (actor_type = 'user' AND actor_user_id IS NOT NULL AND actor_reference IS NULL)
          OR
          (actor_type = 'system' AND actor_user_id IS NULL
            AND actor_reference IN ('SYSTEM_MIGRATION'))
        )"""
    )
    op.execute(
        """ALTER TABLE organization_memberships
        ADD CONSTRAINT ck_organization_memberships_volunteer_finite_period CHECK (
          role <> 'VOLUNTEER'
          OR (valid_from IS NOT NULL AND expires_at IS NOT NULL AND expires_at > valid_from)
        )"""
    )


def downgrade() -> None:
    # Forward recovery is intentional: historical synthetic CRM records remain.
    op.execute(
        "ALTER TABLE organization_memberships DROP CONSTRAINT IF EXISTS "
        "ck_organization_memberships_volunteer_finite_period"
    )
    op.execute(
        "ALTER TABLE audit_records DROP CONSTRAINT IF EXISTS ck_audit_records_actor_identity"
    )
    op.execute("ALTER TABLE audit_records ALTER COLUMN actor_type DROP NOT NULL")
