"""Extend AI jobs into a durable Celery ledger and transactional outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0053_celery_ai_job_ledger"
down_revision = "0052_adoption_growth_diary_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_processing_jobs",
        sa.Column("domain_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ai_processing_jobs",
        sa.Column(
            "execution_backend", sa.String(30), nullable=False, server_default="legacy_polling"
        ),
    )
    op.add_column("ai_processing_jobs", sa.Column("input_snapshot", sa.JSON(), nullable=True))
    op.add_column("ai_processing_jobs", sa.Column("celery_task_id", sa.String(50), nullable=True))
    op.add_column(
        "ai_processing_jobs",
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint("uq_ai_job_target_version", "ai_processing_jobs", type_="unique")
    op.create_unique_constraint(
        "uq_ai_job_target_version",
        "ai_processing_jobs",
        [
            "organization_id",
            "job_type",
            "target_type",
            "target_id",
            "domain_version",
            "model_version",
            "prompt_version",
            "output_schema_version",
        ],
    )
    op.create_index(
        "ix_ai_jobs_backend_status_available",
        "ai_processing_jobs",
        ["execution_backend", "status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_ai_processing_jobs_celery_task_id", "ai_processing_jobs", ["celery_task_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    celery_rows = connection.execute(
        sa.text("SELECT count(*) FROM ai_processing_jobs WHERE execution_backend = 'celery'")
    ).scalar_one()
    duplicate_rows = connection.execute(
        sa.text(
            "SELECT count(*) FROM ("
            " SELECT 1 FROM ai_processing_jobs"
            " GROUP BY organization_id, job_type, target_type, target_id,"
            " model_version, prompt_version, output_schema_version"
            " HAVING count(*) > 1"
            ") AS duplicate_jobs"
        )
    ).scalar_one()
    if celery_rows or duplicate_rows:
        raise RuntimeError(
            "unsafe downgrade: durable Celery jobs or versioned duplicates exist; "
            "keep migration 0053 and use roll-forward recovery"
        )
    op.drop_index("ix_ai_processing_jobs_celery_task_id", table_name="ai_processing_jobs")
    op.drop_index("ix_ai_jobs_backend_status_available", table_name="ai_processing_jobs")
    op.drop_constraint("uq_ai_job_target_version", "ai_processing_jobs", type_="unique")
    op.create_unique_constraint(
        "uq_ai_job_target_version",
        "ai_processing_jobs",
        [
            "organization_id",
            "job_type",
            "target_type",
            "target_id",
            "model_version",
            "prompt_version",
            "output_schema_version",
        ],
    )
    op.drop_column("ai_processing_jobs", "dispatched_at")
    op.drop_column("ai_processing_jobs", "celery_task_id")
    op.drop_column("ai_processing_jobs", "input_snapshot")
    op.drop_column("ai_processing_jobs", "execution_backend")
    op.drop_column("ai_processing_jobs", "domain_version")
