"""毛孩日記後台收件匣：加上已讀/處理狀態欄位，讓工作人員能標記某篇日記已經看過
（見 GrowthDiaryInboxService.set_status）。純粹附加，不影響既有資料。
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_growth_diary_status"
down_revision = "0042_adoption_freetext_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "growth_diary_entries",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
    )


def downgrade() -> None:
    op.drop_column("growth_diary_entries", "status")
