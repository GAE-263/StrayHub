import React, { useState } from "react";
import { Button } from "../../components/ui/button";
import {
  Category,
  categoryLabel,
  CategoryCount,
  ObservationOption,
} from "./observationVocabulary";
import { ObservationOptionCard } from "./ObservationOptionCard";

type Props = {
  category: Category;
  options: ObservationOption[];
  platformOptions: ObservationOption[];
  count?: CategoryCount;
  canManage: boolean;
  forceExpanded?: boolean;
  onEdit: (option: ObservationOption) => void;
  onLifecycle: (
    option: ObservationOption,
    action: "disable" | "restore" | "archive",
  ) => void;
  onAudit: (option: ObservationOption) => void;
  onMove: (option: ObservationOption, direction: -1 | 1) => void;
};

export function ObservationCategoryGroup({
  category,
  options,
  platformOptions,
  count,
  canManage,
  forceExpanded = false,
  onEdit,
  onLifecycle,
  onAudit,
  onMove,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [platformExpanded, setPlatformExpanded] = useState(false);
  const open = expanded || forceExpanded;
  const inactive =
    count?.inactive_count ??
    options.filter((item) => item.status !== "active").length;
  const active =
    count?.active_count ??
    options.filter((item) => item.status === "active").length;
  const custom =
    count?.custom_count ??
    options.filter((item) => item.source === "organization_extension").length;
  return (
    <section
      className="observation-category-group"
      aria-labelledby={`category-${category.id}`}
    >
      <button
        className="observation-category-toggle"
        type="button"
        aria-expanded={open}
        aria-controls={`category-content-${category.id}`}
        onClick={() => setExpanded((value) => !value)}
      >
        <span>
          <strong id={`category-${category.id}`}>
            {categoryLabel(category)}
          </strong>
          <code>{category.code}</code>
        </span>
        <span className="observation-category-counts">
          <span>啟用中 {active}</span>
          <span>自訂 {custom}</span>
          <span>停用／封存 {inactive}</span>
          <span aria-hidden="true">{open ? "收合" : "展開"}</span>
        </span>
      </button>
      {open ? (
        <div
          id={`category-content-${category.id}`}
          className="observation-category-content"
        >
          {options.length > 0 ? (
            <div className="observation-option-section">
              <h3>收容所自訂</h3>
              {options.map((option) => (
                <ObservationOptionCard
                  key={option.id}
                  option={option}
                  canManage={canManage}
                  onEdit={onEdit}
                  onLifecycle={onLifecycle}
                  onAudit={onAudit}
                  onMove={onMove}
                />
              ))}
            </div>
          ) : null}
          {platformOptions.length > 0 ? (
            <div className="observation-option-section platform-option-section">
              <Button
                variant="ghost"
                type="button"
                aria-expanded={platformExpanded}
                aria-controls={`platform-options-${category.id}`}
                onClick={() => setPlatformExpanded((value) => !value)}
              >
                平台預設（{platformOptions.length}）
                {platformExpanded ? "收合" : "展開查看"}
              </Button>
              {platformExpanded ? (
                <div id={`platform-options-${category.id}`}>
                  {platformOptions.map((option) => (
                    <ObservationOptionCard
                      key={option.id}
                      option={option}
                      canManage={false}
                      onEdit={onEdit}
                      onLifecycle={onLifecycle}
                      onAudit={onAudit}
                      onMove={onMove}
                    />
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
