import React from "react";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import {
  Category,
  categoryLabel,
  emptyFilters,
  ObservationFilters as Filters,
  ObservationSource,
  ObservationStatus,
} from "./observationVocabulary";

type Props = {
  categories: Category[];
  filters: Filters;
  matchCount: number;
  onChange: (filters: Filters) => void;
};

export function ObservationFilters({
  categories,
  filters,
  matchCount,
  onChange,
}: Props) {
  const update = (patch: Partial<Filters>) =>
    onChange({ ...filters, ...patch });
  return (
    <Card
      className="observation-filters"
      aria-labelledby="observation-filters-title"
    >
      <CardHeader>
        <div>
          <CardTitle id="observation-filters-title">搜尋與篩選</CardTitle>
          <p className="muted">
            可同時使用中文名稱、stable code、說明、類別、狀態與來源。
          </p>
        </div>
        <strong aria-live="polite">目前符合條件：{matchCount} 個選項</strong>
      </CardHeader>
      <CardContent>
        <div className="observation-filter-grid">
          <Field className="observation-search-field">
            <label htmlFor="observation-search">搜尋觀察詞彙</label>
            <Input
              id="observation-search"
              value={filters.search}
              onChange={(event) => update({ search: event.target.value })}
              placeholder="可搜尋中文名稱、stable code 或說明"
            />
          </Field>
          <Field>
            <label htmlFor="observation-category-filter">觀察類別</label>
            <Select
              id="observation-category-filter"
              value={filters.category}
              onChange={(event) => update({ category: event.target.value })}
            >
              <option value="all">全部類別</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {categoryLabel(category)}（{category.code}）
                </option>
              ))}
            </Select>
          </Field>
          <Field>
            <label htmlFor="observation-status-filter">狀態</label>
            <Select
              id="observation-status-filter"
              value={filters.status}
              onChange={(event) =>
                update({ status: event.target.value as Filters["status"] })
              }
            >
              <option value="all">全部</option>
              <option value="active">啟用中</option>
              <option value="disabled">已停用</option>
              <option value="archived">已封存</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="observation-source-filter">來源</label>
            <Select
              id="observation-source-filter"
              value={filters.source}
              onChange={(event) =>
                update({ source: event.target.value as Filters["source"] })
              }
            >
              <option value="all">全部</option>
              <option value="platform_default">平台預設</option>
              <option value="organization_extension">收容所自訂</option>
            </Select>
          </Field>
        </div>
        <Button
          variant="ghost"
          type="button"
          onClick={() => onChange(emptyFilters)}
          disabled={
            !filters.search &&
            filters.category === "all" &&
            filters.status === "all" &&
            filters.source === "all"
          }
        >
          清除搜尋與篩選
        </Button>
      </CardContent>
    </Card>
  );
}

export type { ObservationSource, ObservationStatus };
