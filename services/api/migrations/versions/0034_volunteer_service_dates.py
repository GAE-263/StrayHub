"""Add independently reviewable volunteer service-date requests."""

from alembic import op

revision = "0034_volunteer_service_dates"
down_revision = "0033_volunteer_pii_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organization_volunteer_access_policies "
        "ADD COLUMN daily_application_limit integer NOT NULL DEFAULT 20"
    )
    op.execute(
        "ALTER TABLE organization_volunteer_access_policies "
        "ADD CONSTRAINT ck_volunteer_access_policy_daily_limit "
        "CHECK (daily_application_limit > 0)"
    )
    op.execute(
        """
        CREATE TABLE volunteer_application_service_dates (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          application_id uuid NOT NULL REFERENCES volunteer_applications(id),
          service_date date NOT NULL,
          status varchar(20) NOT NULL DEFAULT 'pending',
          decided_at timestamptz NULL,
          decided_by_user_id uuid NULL REFERENCES users(id),
          decision_reason varchar(500) NULL,
          version integer NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_volunteer_application_service_date
            UNIQUE (organization_id, application_id, service_date),
          CONSTRAINT ck_volunteer_service_date_status
            CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn'))
        )
        """
    )

    op.execute(
        "CREATE INDEX ix_volunteer_service_dates_org_date_status "
        "ON volunteer_application_service_dates "
        "(organization_id, service_date, status)"
    )
    op.execute("ALTER TABLE volunteer_application_service_dates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE volunteer_application_service_dates FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY volunteer_application_service_dates_tenant_scope
        ON volunteer_application_service_dates
        USING (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
          organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON volunteer_application_service_dates "
        "TO strayhub_runtime"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS volunteer_application_service_dates_tenant_scope "
        "ON volunteer_application_service_dates"
    )
    op.execute("DROP TABLE volunteer_application_service_dates")
    op.execute(
        "ALTER TABLE organization_volunteer_access_policies "
        "DROP CONSTRAINT ck_volunteer_access_policy_daily_limit"
    )
    op.execute(
        "ALTER TABLE organization_volunteer_access_policies "
        "DROP COLUMN daily_application_limit"
    )
