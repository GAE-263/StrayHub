"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Category = {
  id: string;
  code: string;
  display_name: string;
  description: string;
  status: "active" | "disabled";
  display_order: number;
  source: "platform_default" | "organization_extension";
};

type Option = {
  id: string;
  category_id: string;
  organization_id: string | null;
  code: string;
  display_name: string;
  description: string;
  status: "active" | "disabled";
  enabled: boolean;
  display_order: number;
  requires_note: boolean;
  source: "platform_default" | "organization_extension";
  editable: boolean;
};

type Props = {
  apiBaseUrl?: string;
  accessToken?: string;
};

async function responseData<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "操作失敗";
    try {
      const body = (await response.json()) as { message?: string };
      detail = body.message ?? detail;
    } catch {
      // Preserve a safe error when the server does not return JSON.
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

export default function ObservationOptionsPage({
  apiBaseUrl = "",
  accessToken,
}: Props) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [options, setOptions] = useState<Option[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newOrder, setNewOrder] = useState("0");
  const [newRequiresNote, setNewRequiresNote] = useState(false);
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit) => {
      const token = accessToken ?? window.sessionStorage.getItem("access_token");
      const headers = new Headers(init?.headers);
      headers.set("Content-Type", "application/json");
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return responseData<T>(
        await fetch(`${apiBaseUrl}${path}`, { ...init, headers }),
      );
    },
    [accessToken, apiBaseUrl],
  );

  const load = useCallback(async () => {
    const [categoryData, optionData] = await Promise.all([
      request<{ items: Category[] }>("/v1/observation-categories"),
      request<{ items: Option[] }>("/v1/observation-options"),
    ]);
    setCategories(categoryData.items);
    setOptions(optionData.items);
    setCategoryId((current) => current || categoryData.items[0]?.id || "");
  }, [request]);

  useEffect(() => {
    void load().catch((error: Error) => setErrorMessage(error.message));
  }, [load]);

  const runAction = async (action: () => Promise<void>) => {
    setErrorMessage("");
    setMessage("");
    try {
      await action();
      await load();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "操作失敗");
    }
  };

  const createOption = async (event: FormEvent) => {
    event.preventDefault();
    await runAction(async () => {
      await request<Option>("/v1/observation-options", {
        method: "POST",
        body: JSON.stringify({
          category_id: categoryId,
          code: newCode,
          display_name: newName,
          description: newDescription,
          display_order: Number(newOrder),
          requires_note: newRequiresNote,
        }),
      });
      setNewCode("");
      setNewName("");
      setNewDescription("");
      setMessage("收容所觀察選項已建立。");
    });
  };

  const updateOption = async (option: Option, patch: Partial<Option>) => {
    await runAction(async () => {
      await request<Option>(`/v1/observation-options/${option.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setMessage("觀察選項已更新，歷史 Code 不變。");
    });
  };

  const moveOption = async (option: Option, direction: -1 | 1) => {
    const siblings = options
      .filter((item) => item.category_id === option.category_id && item.editable)
      .sort((left, right) => left.display_order - right.display_order);
    const index = siblings.findIndex((item) => item.id === option.id);
    const target = siblings[index + direction];
    if (!target) return;
    await updateOption(option, { display_order: target.display_order });
    await updateOption(target, { display_order: option.display_order });
  };

  const categoryNameById = useMemo(
    () => new Map(categories.map((category) => [category.id, category.display_name])),
    [categories],
  );

  return (
    <main aria-labelledby="observation-options-title">
      <h1 id="observation-options-title">標準化觀察語彙管理</h1>
      <p>平台預設提供穩定 Code；收容所擴充可以改名、排序與停用，歷史回報仍保留原始顯示快照。</p>
      <p role="alert" hidden={!errorMessage}>授權或操作失敗：{errorMessage}</p>
      <p role="status" hidden={!message}>{message}</p>

      <section aria-labelledby="observation-category-title">
        <h2 id="observation-category-title">觀察類別與來源</h2>
        <ul>
          {categories.map((category) => (
            <li key={category.id}>
              {category.display_name}（{category.source === "platform_default" ? "平台預設" : "收容所擴充"}）
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="observation-create-title">
        <h2 id="observation-create-title">建立收容所擴充選項</h2>
        <form onSubmit={(event) => void createOption(event)}>
          <label htmlFor="observation-category">觀察類別</label>
          <select
            id="observation-category"
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value)}
            required
          >
            <option value="">請選擇</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.display_name}
              </option>
            ))}
          </select>
          <label htmlFor="observation-code">穩定 Code</label>
          <input id="observation-code" value={newCode} onChange={(event) => setNewCode(event.target.value)} required />
          <label htmlFor="observation-name">顯示名稱</label>
          <input id="observation-name" value={newName} onChange={(event) => setNewName(event.target.value)} required />
          <label htmlFor="observation-description">說明</label>
          <input id="observation-description" value={newDescription} onChange={(event) => setNewDescription(event.target.value)} />
          <label htmlFor="observation-order">顯示順序</label>
          <input id="observation-order" type="number" min="0" value={newOrder} onChange={(event) => setNewOrder(event.target.value)} />
          <label>
            <input type="checkbox" checked={newRequiresNote} onChange={(event) => setNewRequiresNote(event.target.checked)} />
            需要補充說明
          </label>
          <button type="submit">建立選項</button>
        </form>
      </section>

      <section aria-labelledby="observation-list-title">
        <h2 id="observation-list-title">有效與歷史選項（可改名、排序或停用收容所擴充）</h2>
        <ul>
          {options.map((option) => (
            <li key={option.id}>
              <span>
                {option.display_name}（{option.code}）／{categoryNameById.get(option.category_id) ?? "未知類別"}／
                {option.source === "platform_default" ? "平台預設" : "收容所擴充"}／
                {option.enabled ? "啟用" : "已停用，僅供歷史顯示"}
              </span>
              {option.editable && (
                <>
                  <label htmlFor={`rename-${option.id}`}>顯示名稱</label>
                  <input id={`rename-${option.id}`} defaultValue={option.display_name} />
                  <button
                    type="button"
                    onClick={(event) => {
                      const input = event.currentTarget.previousElementSibling as HTMLInputElement | null;
                      void updateOption(option, { display_name: input?.value ?? option.display_name });
                    }}
                  >
                    儲存改名
                  </button>
                  <button type="button" onClick={() => void moveOption(option, -1)}>上移</button>
                  <button type="button" onClick={() => void moveOption(option, 1)}>下移</button>
                  {option.enabled && (
                    <button type="button" onClick={() => void updateOption(option, { enabled: false })}>
                      停用
                    </button>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
