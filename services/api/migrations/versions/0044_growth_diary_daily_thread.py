"""毛孩日記改成「一天一篇」：同一天內連續分享的照片/文字合併進同一篇
GrowthDiaryEntry，隔天才開新的一篇（見 line_webhook.py 的
_handle_growth_diary_message／GrowthDiaryRepository.append_to_entry）。

- growth_diary_entries.photo_key（單張）→ photo_keys（JSON 陣列，當天每張
  照片都存進去，AI 只分析最新一張）。既有資料原樣搬進陣列，不遺失。
- growth_diary_drafts 不再是「存完一則訊息就砍掉」的暫存記號，而是持續存在
  的「目前對話串」；新增 current_entry_id／entry_date 記錄「今天的訊息要接
  到哪一篇、是哪一天開的」，讓 webhook 判斷該接續同一篇還是開新的一篇。
"""

import sqlalchemy as sa
from alembic import op

revision = "0044_growth_diary_daily_thread"
down_revision = "0043_growth_diary_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "growth_diary_entries",
        sa.Column("photo_keys", sa.JSON, nullable=False, server_default="[]"),
    )
    op.execute(
        """
        UPDATE growth_diary_entries
        SET photo_keys = json_build_array(photo_key)
        WHERE photo_key IS NOT NULL
        """
    )
    op.drop_column("growth_diary_entries", "photo_key")

    op.add_column(
        "growth_diary_drafts",
        sa.Column(
            "current_entry_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("growth_diary_entries.id"),
            nullable=True,
        ),
    )
    op.add_column("growth_diary_drafts", sa.Column("entry_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("growth_diary_drafts", "entry_date")
    op.drop_column("growth_diary_drafts", "current_entry_id")

    op.add_column("growth_diary_entries", sa.Column("photo_key", sa.String(500)))
    op.execute(
        """
        UPDATE growth_diary_entries
        SET photo_key = photo_keys ->> (json_array_length(photo_keys) - 1)
        WHERE json_array_length(photo_keys) > 0
        """
    )
    op.drop_column("growth_diary_entries", "photo_keys")
