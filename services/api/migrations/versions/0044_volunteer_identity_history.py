"""Volunteer identity profile, service labels, notes, incidents and restrictions."""

from alembic import op

revision = "0044_volunteer_identity_history"
down_revision = "0043_volunteer_surname_display"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "organization_volunteer_number_counters",
    "volunteer_notes",
    "volunteer_incidents",
    "volunteer_restrictions",
)


def _tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {table}_tenant_scope ON {table}
        USING (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )"""
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organization_memberships ADD CONSTRAINT "
        "uq_organization_memberships_org_id UNIQUE (organization_id, id)"
    )
    op.execute("ALTER TABLE organization_memberships ADD COLUMN volunteer_no varchar(20) NULL")
    op.execute(
        "ALTER TABLE organization_memberships ADD COLUMN "
        "can_assist_new_volunteers boolean NOT NULL DEFAULT false"
    )
    op.execute(
        """WITH numbered AS (
          SELECT id, row_number() OVER (
            PARTITION BY organization_id ORDER BY created_at, id
          ) AS sequence_no
          FROM organization_memberships
          WHERE role = 'VOLUNTEER'
        )
        UPDATE organization_memberships membership
        SET volunteer_no = 'V' || lpad(numbered.sequence_no::text, 3, '0')
        FROM numbered WHERE numbered.id = membership.id"""
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_memberships_org_volunteer_no "
        "ON organization_memberships (organization_id, volunteer_no) "
        "WHERE volunteer_no IS NOT NULL"
    )

    op.execute(
        """CREATE TABLE volunteer_profiles (
          user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          surname varchar(20) NULL,
          preferred_display_name varchar(100) NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute(
        """INSERT INTO volunteer_profiles (user_id, surname, created_at, updated_at)
        SELECT user_id, max(volunteer_surname), min(created_at), now()
        FROM organization_memberships
        WHERE role = 'VOLUNTEER'
        GROUP BY user_id"""
    )
    op.execute("ALTER TABLE organization_memberships DROP COLUMN volunteer_surname")
    op.execute("ALTER TABLE volunteer_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE volunteer_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY volunteer_profiles_authorized_scope ON volunteer_profiles
        USING (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
          OR EXISTS (
            SELECT 1 FROM organization_memberships membership
            WHERE membership.user_id = volunteer_profiles.user_id
              AND membership.organization_id::text =
                NULLIF(current_setting('app.current_org_id', true), '')
          )
          OR EXISTS (
            SELECT 1 FROM volunteer_applications application
            WHERE application.user_id = volunteer_profiles.user_id
              AND application.organization_id::text =
                NULLIF(current_setting('app.current_org_id', true), '')
          )
        )
        WITH CHECK (
          COALESCE(current_setting('app.platform_scope', true), 'false') = 'true'
          OR user_id::text = NULLIF(current_setting('app.auth_user_id', true), '')
          OR EXISTS (
            SELECT 1 FROM volunteer_applications application
            WHERE application.user_id = volunteer_profiles.user_id
              AND application.organization_id::text =
                NULLIF(current_setting('app.current_org_id', true), '')
          )
        )"""
    )

    op.execute(
        """CREATE TABLE organization_volunteer_number_counters (
          organization_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
          next_value integer NOT NULL DEFAULT 1 CHECK (next_value > 0),
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute(
        """INSERT INTO organization_volunteer_number_counters
          (organization_id, next_value, created_at, updated_at)
        SELECT organization_id, count(*) + 1, now(), now()
        FROM organization_memberships WHERE role = 'VOLUNTEER'
        GROUP BY organization_id"""
    )
    op.execute(
        """INSERT INTO organization_volunteer_number_counters
          (organization_id, next_value, created_at, updated_at)
        SELECT id, 1, now(), now() FROM organizations
        ON CONFLICT (organization_id) DO NOTHING"""
    )

    op.execute(
        """CREATE TABLE volunteer_notes (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          subject_membership_id uuid NOT NULL,
          author_membership_id uuid NOT NULL,
          content varchar(2000) NOT NULL CHECK (length(trim(content)) > 0),
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_volunteer_notes_subject_membership_scope FOREIGN KEY
            (organization_id, subject_membership_id)
            REFERENCES organization_memberships (organization_id, id),
          CONSTRAINT fk_volunteer_notes_author_membership_scope FOREIGN KEY
            (organization_id, author_membership_id)
            REFERENCES organization_memberships (organization_id, id)
        )"""
    )
    op.execute(
        "CREATE INDEX ix_volunteer_notes_org_subject_created ON volunteer_notes "
        "(organization_id, subject_membership_id, created_at DESC)"
    )

    op.execute(
        """CREATE TABLE volunteer_incidents (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          subject_membership_id uuid NOT NULL,
          volunteer_user_id uuid NOT NULL REFERENCES users(id),
          incident_type varchar(80) NOT NULL,
          severity varchar(20) NOT NULL CHECK (severity IN ('low','medium','high','critical')),
          factual_summary varchar(2000) NOT NULL,
          occurred_at timestamptz NOT NULL,
          created_by_membership_id uuid NOT NULL,
          status varchar(20) NOT NULL DEFAULT 'reported'
            CHECK (status IN ('reported','under_review','confirmed','dismissed')),
          reviewed_by_user_id uuid NULL REFERENCES users(id),
          reviewed_at timestamptz NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_volunteer_incidents_org_id UNIQUE (organization_id, id),
          CONSTRAINT ck_volunteer_incidents_content CHECK (
            length(trim(incident_type)) > 0 AND length(trim(factual_summary)) > 0),
          CONSTRAINT fk_volunteer_incidents_subject_membership_scope FOREIGN KEY
            (organization_id, subject_membership_id)
            REFERENCES organization_memberships (organization_id, id),
          CONSTRAINT fk_volunteer_incidents_creator_membership_scope FOREIGN KEY
            (organization_id, created_by_membership_id)
            REFERENCES organization_memberships (organization_id, id)
        )"""
    )
    op.execute(
        "CREATE INDEX ix_volunteer_incidents_org_subject_occurred ON volunteer_incidents "
        "(organization_id, subject_membership_id, occurred_at DESC)"
    )

    op.execute(
        """CREATE TABLE volunteer_restrictions (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES organizations(id),
          volunteer_user_id uuid NOT NULL REFERENCES users(id),
          incident_id uuid NOT NULL,
          scope varchar(20) NOT NULL CHECK (scope IN ('SHELTER','PLATFORM')),
          reason_category varchar(80) NOT NULL,
          status varchar(20) NOT NULL DEFAULT 'pending_review'
            CHECK (status IN ('pending_review','active','rejected','expired','revoked')),
          starts_at timestamptz NOT NULL DEFAULT now(),
          ends_at timestamptz NULL,
          requested_by_membership_id uuid NOT NULL,
          approved_by_user_id uuid NULL REFERENCES users(id),
          reviewed_at timestamptz NULL,
          decision_reason varchar(500) NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_volunteer_restrictions_period CHECK
            (ends_at IS NULL OR ends_at > starts_at),
          CONSTRAINT ck_volunteer_restrictions_active_review CHECK
            (status <> 'active' OR
              (approved_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)),
          CONSTRAINT fk_volunteer_restrictions_incident_scope FOREIGN KEY
            (organization_id, incident_id)
            REFERENCES volunteer_incidents (organization_id, id),
          CONSTRAINT fk_volunteer_restrictions_requester_scope FOREIGN KEY
            (organization_id, requested_by_membership_id)
            REFERENCES organization_memberships (organization_id, id)
        )"""
    )
    op.execute(
        "CREATE INDEX ix_volunteer_restrictions_subject_active ON volunteer_restrictions "
        "(volunteer_user_id, scope, status, starts_at, ends_at)"
    )
    op.execute(
        "CREATE INDEX ix_volunteer_restrictions_org_created ON volunteer_restrictions "
        "(organization_id, created_at DESC)"
    )

    for table in TENANT_TABLES:
        _tenant_rls(table)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_scope ON {table}")
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP POLICY IF EXISTS volunteer_profiles_authorized_scope ON volunteer_profiles")
    op.execute("ALTER TABLE organization_memberships ADD COLUMN volunteer_surname varchar(20) NULL")
    op.execute(
        """UPDATE organization_memberships membership
        SET volunteer_surname = profile.surname
        FROM volunteer_profiles profile
        WHERE profile.user_id = membership.user_id"""
    )
    op.execute("DROP TABLE volunteer_profiles")
    op.execute("DROP INDEX IF EXISTS uq_memberships_org_volunteer_no")
    op.execute("ALTER TABLE organization_memberships DROP COLUMN can_assist_new_volunteers")
    op.execute("ALTER TABLE organization_memberships DROP COLUMN volunteer_no")
    op.execute(
        "ALTER TABLE organization_memberships DROP CONSTRAINT uq_organization_memberships_org_id"
    )
