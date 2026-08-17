"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { authFetch } from "../../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/management/StateViews";
import { ObservationAuditPanel } from "./ObservationAuditPanel";
import { ObservationCategoryGroup } from "./ObservationCategoryGroup";
import { ObservationFilters } from "./ObservationFilters";
import {
  ObservationLifecycleDialog,
  Action,
} from "./ObservationLifecycleDialog";
import { ObservationOptionForm, FormValue } from "./ObservationOptionForm";
import { ObservationSummary } from "./ObservationSummary";
import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import {
  Category,
  emptyFilters,
  filteredOptions,
  groupedOptions,
  ObservationFilters as Filters,
  ObservationList,
  ObservationOption,
  Summary,
} from "./observationVocabulary";

async function responseData<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "操作失敗，請稍後再試。";
    try {
      const body = (await response.json()) as { message?: string };
      detail = body.message ?? detail;
    } catch {
      // Keep a safe Traditional Chinese message when the body is unavailable.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export default function ObservationVocabularyPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [options, setOptions] = useState<ObservationOption[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [categoryCounts, setCategoryCounts] = useState<
    ObservationList["category_counts"]
  >([]);
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [formOption, setFormOption] = useState<
    ObservationOption | null | undefined
  >(undefined);
  const [lifecycle, setLifecycle] = useState<{
    option: ObservationOption;
    action: Action;
  } | null>(null);
  const [auditOption, setAuditOption] = useState<ObservationOption | null>(
    null,
  );
  const formTrigger = useRef<HTMLElement | null>(null);
  const lifecycleTrigger = useRef<HTMLElement | null>(null);
  const auditTrigger = useRef<HTMLElement | null>(null);

  const rememberActiveElement = (target: { current: HTMLElement | null }) => {
    target.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
  };
  const restoreFocus = (target: { current: HTMLElement | null }) => {
    const element = target.current;
    target.current = null;
    if (element?.isConnected) window.setTimeout(() => element.focus(), 0);
  };

  const request = useCallback(async <T,>(path: string, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    return responseData<T>(await authFetch(path, { ...init, headers }));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [categoryData, optionData] = await Promise.all([
        request<{ items: Category[] }>("/v1/observation-categories"),
        request<ObservationList>("/v1/observation-options"),
      ]);
      setCategories(categoryData.items);
      setOptions(optionData.items);
      setSummary(optionData.summary);
      setCategoryCounts(optionData.category_counts);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "觀察詞彙載入失敗，請重新載入。",
      );
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(
    () => groupedOptions(categories, options, filters),
    [categories, filters, options],
  );
  const matches = useMemo(
    () => filteredOptions(options, filters),
    [options, filters],
  );
  const canManage = summary?.scope === "admin_full";
  const filtersActive =
    Boolean(filters.search) ||
    filters.category !== "all" ||
    filters.status !== "all" ||
    filters.source !== "all";

  const runAction = async (action: () => Promise<void>, success: string) => {
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(success);
      setFormOption(undefined);
      if (formOption !== undefined) restoreFocus(formTrigger);
      if (lifecycle) {
        setLifecycle(null);
        restoreFocus(lifecycleTrigger);
      }
      await load();
    } catch (actionError) {
      throw actionError;
    }
  };

  const saveOption = async (value: FormValue) => {
    if (!value.category_id) throw new Error("請選擇觀察類別。");
    const body = {
      category_id: value.category_id,
      code: value.code.trim(),
      display_name: value.display_name.trim(),
      description: value.description,
      display_order: Number(value.display_order),
      requires_note: value.requires_note,
    };
    if (formOption) {
      await runAction(
        () =>
          request(`/v1/observation-options/${formOption.id}`, {
            method: "PATCH",
            body: JSON.stringify({
              code: body.code,
              display_name: body.display_name,
              description: body.description,
              display_order: body.display_order,
              requires_note: body.requires_note,
              expected_updated_at: formOption.updated_at,
            }),
          }).then(() => undefined),
        "觀察選項已儲存。",
      );
    } else {
      await runAction(
        () =>
          request("/v1/observation-options", {
            method: "POST",
            body: JSON.stringify(body),
          }).then(() => undefined),
        "觀察選項已新增。",
      );
    }
  };

  const moveOption = async (option: ObservationOption, direction: -1 | 1) => {
    const siblings = options
      .filter(
        (item) =>
          item.category_id === option.category_id &&
          item.source === "organization_extension" &&
          item.status !== "archived",
      )
      .sort((a, b) => a.display_order - b.display_order);
    const index = siblings.findIndex((item) => item.id === option.id);
    const target = siblings[index + direction];
    if (!target) return;
    const reordered = siblings.map((item, itemIndex) => ({
      option_id: item.id,
      display_order:
        itemIndex === index
          ? target.display_order
          : itemIndex === index + direction
            ? option.display_order
            : item.display_order,
    }));
    await runAction(
      () =>
        request("/v1/observation-options/reorder", {
          method: "POST",
          body: JSON.stringify({ items: reordered }),
        }).then(() => undefined),
      "觀察選項順序已更新。",
    );
  };

  return (
    <main aria-labelledby="observation-options-title">
      <div className="page-heading observation-page-heading">
        <div>
          <span className="eyebrow">OBSERVATION VOCABULARY</span>
          <h1 id="observation-options-title">觀察詞彙</h1>
          <p>
            用於日常照護回報的現場觀察描述；標準化觀察語彙管理會優先使用台灣繁體中文。
            平台預設與收容所自訂資料清楚區分；穩定 Code（stable
            code）僅作次要技術資訊。
            管理者可用「新增選項」建立內容，停用後不會出現在新的回報表單，歷史回報仍保留原始顯示快照。
          </p>
        </div>
        {canManage ? (
          <Button
            type="button"
            onClick={(event) => {
              formTrigger.current = event.currentTarget;
              setFormOption(null);
            }}
          >
            新增選項
          </Button>
        ) : null}
      </div>

      {message ? (
        <p className="notice success" role="status">
          {message}
        </p>
      ) : null}
      {error ? (
        <Alert role="alert" className="p1-error">
          <div>
            <strong>觀察詞彙載入或操作失敗</strong>
            <p>{error}</p>
          </div>
          <Button variant="secondary" type="button" onClick={() => void load()}>
            重新載入
          </Button>
        </Alert>
      ) : null}
      {loading && !summary ? (
        <LoadingState
          title="正在載入觀察詞彙…"
          description="摘要載入完成後才會顯示數量。"
        />
      ) : null}
      {!loading && !error && categories.length === 0 ? (
        <EmptyState
          title="目前沒有可查看的觀察詞彙"
          description="請確認目前收容所情境與查看權限。"
        />
      ) : null}

      <ObservationSummary summary={summary} loading={loading} />
      {summary?.scope === "admin_full" ? (
        <Card
          className="source-explanation"
          aria-labelledby="source-explanation-title"
        >
          <CardHeader>
            <CardTitle id="source-explanation-title">
              平台預設與收容所自訂
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p>
              <strong>平台預設</strong>
              是平台提供的共同基礎詞彙，收容所可以查看與使用，但不能從本頁改寫。
            </p>
            <p>
              <strong>收容所自訂</strong>
              只屬於目前收容所，具設定管理權限者可以新增、編輯、排序、停用、恢復或封存。
            </p>
            <p>停用或封存不會刪除歷史回報；只會影響新的回報表單是否顯示。</p>
          </CardContent>
        </Card>
      ) : null}

      {summary ? (
        <ObservationFilters
          categories={categories}
          filters={filters}
          matchCount={matches.length}
          onChange={setFilters}
        />
      ) : null}

      {summary && !loading && groups.length === 0 ? (
        <EmptyState
          title={
            filtersActive
              ? "找不到符合條件的觀察詞彙"
              : "目前沒有可顯示的觀察詞彙"
          }
          description={
            filtersActive
              ? "請調整條件，或清除搜尋與篩選後再試。"
              : "目前沒有可使用或可管理的選項。"
          }
        />
      ) : null}
      <section className="observation-category-list" aria-label="觀察類別">
        {groups.map(({ category, custom, platform }) => (
          <ObservationCategoryGroup
            key={category.id}
            category={category}
            options={custom}
            platformOptions={platform}
            count={categoryCounts.find(
              (item) => item.category_id === category.id,
            )}
            canManage={Boolean(canManage)}
            forceExpanded={filtersActive}
            onEdit={(option) => {
              rememberActiveElement(formTrigger);
              setFormOption(option);
            }}
            onLifecycle={(option, action) => {
              rememberActiveElement(lifecycleTrigger);
              setLifecycle({ option, action });
            }}
            onAudit={(option) => {
              rememberActiveElement(auditTrigger);
              setAuditOption(option);
            }}
            onMove={(option, direction) => void moveOption(option, direction)}
          />
        ))}
      </section>

      {formOption !== undefined ? (
        <ObservationOptionForm
          categories={categories}
          option={formOption}
          onSubmit={saveOption}
          onCancel={() => {
            setFormOption(undefined);
            restoreFocus(formTrigger);
          }}
        />
      ) : null}
      {lifecycle ? (
        <ObservationLifecycleDialog
          option={lifecycle.option}
          action={lifecycle.action}
          onCancel={() => {
            setLifecycle(null);
            restoreFocus(lifecycleTrigger);
          }}
          onConfirm={() =>
            runAction(
              () =>
                request(
                  `/v1/observation-options/${lifecycle.option.id}/${lifecycle.action}`,
                  {
                    method: "POST",
                    body: JSON.stringify({}),
                  },
                ).then(() => undefined),
              `觀察選項已${lifecycle.action === "disable" ? "停用" : lifecycle.action === "restore" ? "恢復" : "封存"}。`,
            )
          }
        />
      ) : null}
      {auditOption ? (
        <ObservationAuditPanel
          option={auditOption}
          onClose={() => {
            setAuditOption(null);
            restoreFocus(auditTrigger);
          }}
        />
      ) : null}
    </main>
  );
}
