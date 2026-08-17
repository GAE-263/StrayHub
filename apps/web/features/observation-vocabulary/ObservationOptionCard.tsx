import React from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  ObservationOption,
  optionSourceLabel,
  optionStatusLabel,
} from "./observationVocabulary";

type Props = {
  option: ObservationOption;
  canManage: boolean;
  onEdit: (option: ObservationOption) => void;
  onLifecycle: (
    option: ObservationOption,
    action: "disable" | "restore" | "archive",
  ) => void;
  onAudit: (option: ObservationOption) => void;
  onMove: (option: ObservationOption, direction: -1 | 1) => void;
};

export function ObservationOptionCard({
  option,
  canManage,
  onEdit,
  onLifecycle,
  onAudit,
  onMove,
}: Props) {
  const custom = option.source === "organization_extension";
  return (
    <article
      className="observation-option-card"
      aria-label={option.display_name}
    >
      <div className="observation-option-main">
        <h4>{option.display_name}</h4>
        <p className="observation-option-description">
          {option.description || "目前沒有補充說明。"}
        </p>
      </div>
      <div className="observation-option-meta">
        <Badge>{optionStatusLabel(option.status)}</Badge>
        <Badge className="badge-source">
          {optionSourceLabel(option.source)}
        </Badge>
        <code>{option.code}</code>
        {option.requires_note ? <span>需要補充說明</span> : null}
        <span>最後修改：{option.last_modified_by ?? "系統"}</span>
        <time dateTime={option.last_modified_at}>
          {new Date(option.last_modified_at).toLocaleString("zh-TW")}
        </time>
        {option.has_historical_usage ? (
          <span className="history-note">
            已有歷史回報使用（{option.historical_usage_count} 筆）
          </span>
        ) : null}
      </div>
      {canManage && custom ? (
        <div
          className="observation-option-actions"
          aria-label={`${option.display_name} 操作`}
        >
          <Button
            variant="secondary"
            type="button"
            onClick={() => onEdit(option)}
          >
            編輯
          </Button>
          <Button
            variant="secondary"
            type="button"
            onClick={() => onMove(option, -1)}
          >
            上移
          </Button>
          <Button
            variant="secondary"
            type="button"
            onClick={() => onMove(option, 1)}
          >
            下移
          </Button>
          {option.status === "active" ? (
            <>
              <Button
                variant="destructive"
                type="button"
                onClick={() => onLifecycle(option, "disable")}
              >
                停用
              </Button>
              <Button
                variant="secondary"
                type="button"
                onClick={() => onLifecycle(option, "archive")}
              >
                封存
              </Button>
            </>
          ) : (
            <Button
              variant="secondary"
              type="button"
              onClick={() => onLifecycle(option, "restore")}
            >
              恢復
            </Button>
          )}
          <Button variant="ghost" type="button" onClick={() => onAudit(option)}>
            查看變更紀錄
          </Button>
        </div>
      ) : null}
    </article>
  );
}
