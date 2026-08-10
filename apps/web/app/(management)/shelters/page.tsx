"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { authFetch } from "../../../lib/auth";

type Shelter = {
  id: string;
  code: string;
  name: string;
  status: "pending_setup" | "active" | "suspended";
};

type Membership = {
  id: string;
  organization_id: string;
  user_id: string;
  role: "SHELTER_ADMIN" | "STAFF" | "VOLUNTEER";
  status: "invited" | "active" | "disabled";
};

type Area = {
  id: string;
  name: string;
  area_type: "area" | "cage";
  status: "active" | "inactive";
};

async function responseData<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "操作失敗";
    try {
      const body = (await response.json()) as { message?: string };
      detail = body.message ?? detail;
    } catch {
      // Keep a safe generic message when the server response is not JSON.
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export default function SheltersManagementPage() {
  const [shelters, setShelters] = useState<Shelter[]>([]);
  const [selectedShelterId, setSelectedShelterId] = useState("");
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [newShelterName, setNewShelterName] = useState("");
  const [organizationCode, setOrganizationCode] = useState("");
  const [initialAdminUsername, setInitialAdminUsername] = useState("");
  const [initialAdminPassword, setInitialAdminPassword] = useState("");
  const [accountUsername, setAccountUsername] = useState("");
  const [accountDisplayName, setAccountDisplayName] = useState("");
  const [accountPassword, setAccountPassword] = useState("");
  const [accountRole, setAccountRole] = useState<Membership["role"]>("STAFF");
  const [areaName, setAreaName] = useState("");
  const [areaType, setAreaType] = useState<Area["area_type"]>("area");
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const selectedShelter = useMemo(
    () => shelters.find((shelter) => shelter.id === selectedShelterId),
    [shelters, selectedShelterId],
  );

  const request = useCallback(async <T,>(path: string, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    const response = await authFetch(path, {
      ...init,
      headers,
    });
    return responseData<T>(response);
  }, []);

  const loadShelters = useCallback(
    async (preferredId?: string) => {
      const data = await request<{ items: Shelter[] }>("/v1/organizations");
      setShelters(data.items);
      const nextId = preferredId ?? selectedShelterId;
      if (data.items.some((shelter) => shelter.id === nextId)) {
        setSelectedShelterId(nextId);
      } else if (data.items[0]) {
        setSelectedShelterId(data.items[0].id);
      }
    },
    [request, selectedShelterId],
  );

  const loadShelterDetails = useCallback(async () => {
    if (!selectedShelterId) return;
    const [membershipData, areaData] = await Promise.all([
      request<{ items: Membership[] }>(
        `/v1/organizations/${selectedShelterId}/memberships`,
      ),
      selectedShelter?.status === "active"
        ? request<{ items: Area[] }>(
            `/v1/organizations/${selectedShelterId}/areas`,
          )
        : Promise.resolve({ items: [] as Area[] }),
    ]);
    setMemberships(membershipData.items);
    setAreas(areaData.items);
  }, [request, selectedShelter, selectedShelterId]);

  useEffect(() => {
    void loadShelters().catch((error: Error) => setErrorMessage(error.message));
  }, [loadShelters]);

  useEffect(() => {
    const shelter = shelters.find((item) => item.id === selectedShelterId);
    void loadShelterDetails().catch((error: Error) =>
      setErrorMessage(error.message),
    );
  }, [loadShelterDetails, selectedShelterId, shelters]);

  const submit = async (event: FormEvent, action: () => Promise<void>) => {
    event.preventDefault();
    await runAction(action);
  };

  const runAction = async (action: () => Promise<void>) => {
    setErrorMessage("");
    setMessage("");
    try {
      await action();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "操作失敗");
    }
  };

  const createShelter = async () => {
    const data = await request<Shelter>("/v1/organizations", {
      method: "POST",
      body: JSON.stringify({
        code: organizationCode,
        name: newShelterName,
        status: "pending_setup",
        initial_admin_username: initialAdminUsername,
        initial_admin_temporary_password: initialAdminPassword,
      }),
    });
    setMessage("收容所已建立，仍須平台管理員啟用後才能建立一般業務資料。");
    await loadShelters(data.id);
  };

  const activateShelter = async () => {
    if (!selectedShelterId) return;
    await request<Shelter>(`/v1/organizations/${selectedShelterId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "active" }),
    });
    setMessage("收容所已啟用。");
    await loadShelters(selectedShelterId);
  };

  const createAccount = async () => {
    await request<Membership>(
      `/v1/organizations/${selectedShelterId}/accounts`,
      {
        method: "POST",
        body: JSON.stringify({
          username: accountUsername,
          display_name: accountDisplayName,
          temporary_password: accountPassword,
          role: accountRole,
        }),
      },
    );
    setMessage("帳號與 Membership 已建立。");
    setAccountUsername("");
    setAccountDisplayName("");
    setAccountPassword("");
    await loadShelterDetails();
  };

  const updateMembership = async (
    membershipId: string,
    changes: Partial<Pick<Membership, "role" | "status">>,
  ) => {
    await request<Membership>(
      `/v1/organizations/${selectedShelterId}/memberships/${membershipId}`,
      {
        method: "PATCH",
        body: JSON.stringify(changes),
      },
    );
    setMessage("Membership 已更新並寫入 Audit。");
    await loadShelterDetails();
  };

  const createArea = async () => {
    await request<Area>(`/v1/organizations/${selectedShelterId}/areas`, {
      method: "POST",
      body: JSON.stringify({ name: areaName, area_type: areaType }),
    });
    setMessage("Cage/Area 已建立。");
    setAreaName("");
    await loadShelterDetails();
  };

  return (
    <main aria-labelledby="shelter-management-title">
      <h1 id="shelter-management-title">收容所與帳號管理</h1>
      <p>所有資料操作都由後端依驗證後的機構範圍判定。</p>
      {errorMessage && <p role="alert">授權或操作失敗：{errorMessage}</p>}
      {message && <p role="status">{message}</p>}

      <section aria-labelledby="shelter-list-title">
        <h2 id="shelter-list-title">收容所</h2>
        <label htmlFor="selected-shelter">目前管理收容所</label>
        <select
          id="selected-shelter"
          value={selectedShelterId}
          onChange={(event) => setSelectedShelterId(event.target.value)}
        >
          <option value="">請選擇</option>
          {shelters.map((shelter) => (
            <option key={shelter.id} value={shelter.id}>
              {shelter.name}（{shelter.status}）
            </option>
          ))}
        </select>
        {selectedShelter?.status === "pending_setup" && (
          <button type="button" onClick={() => void runAction(activateShelter)}>
            啟用收容所
          </button>
        )}
        <form onSubmit={(event) => void submit(event, createShelter)}>
          <h3>建立收容所</h3>
          <label htmlFor="shelter-code">機構代碼</label>
          <input
            id="shelter-code"
            value={organizationCode}
            onChange={(event) => setOrganizationCode(event.target.value)}
            required
          />
          <label htmlFor="shelter-name">收容所名稱</label>
          <input
            id="shelter-name"
            value={newShelterName}
            onChange={(event) => setNewShelterName(event.target.value)}
            required
          />
          <label htmlFor="initial-admin-username">初始管理員帳號</label>
          <input
            id="initial-admin-username"
            value={initialAdminUsername}
            onChange={(event) => setInitialAdminUsername(event.target.value)}
            required
          />
          <label htmlFor="initial-admin-password">初始管理員暫時密碼</label>
          <input
            id="initial-admin-password"
            type="password"
            value={initialAdminPassword}
            onChange={(event) => setInitialAdminPassword(event.target.value)}
            required
          />
          <button type="submit">建立收容所</button>
        </form>
      </section>

      <section aria-labelledby="account-list-title">
        <h2 id="account-list-title">帳號與 Membership</h2>
        <ul>
          {memberships.map((membership) => (
            <li key={membership.id}>
              <span>
                {membership.user_id}（{membership.status}）
              </span>
              <select
                aria-label={`${membership.user_id} 角色`}
                defaultValue={membership.role}
                onChange={(event) =>
                  void runAction(() =>
                    updateMembership(membership.id, {
                      role: event.target.value as Membership["role"],
                    }),
                  )
                }
              >
                <option value="SHELTER_ADMIN">SHELTER_ADMIN</option>
                <option value="STAFF">STAFF</option>
                <option value="VOLUNTEER">VOLUNTEER</option>
              </select>
              <button
                type="button"
                disabled={membership.status === "disabled"}
                onClick={() =>
                  void runAction(() =>
                    updateMembership(membership.id, { status: "disabled" }),
                  )
                }
              >
                停用
              </button>
            </li>
          ))}
        </ul>
        <form onSubmit={(event) => void submit(event, createAccount)}>
          <h3>建立機構帳號</h3>
          <label htmlFor="account-username">帳號</label>
          <input
            id="account-username"
            value={accountUsername}
            onChange={(event) => setAccountUsername(event.target.value)}
            required
          />
          <label htmlFor="account-display-name">顯示名稱</label>
          <input
            id="account-display-name"
            value={accountDisplayName}
            onChange={(event) => setAccountDisplayName(event.target.value)}
            required
          />
          <label htmlFor="account-password">暫時密碼</label>
          <input
            id="account-password"
            type="password"
            value={accountPassword}
            onChange={(event) => setAccountPassword(event.target.value)}
            required
          />
          <label htmlFor="account-role">角色</label>
          <select
            id="account-role"
            value={accountRole}
            onChange={(event) =>
              setAccountRole(event.target.value as Membership["role"])
            }
          >
            <option value="SHELTER_ADMIN">SHELTER_ADMIN</option>
            <option value="STAFF">STAFF</option>
            <option value="VOLUNTEER">VOLUNTEER</option>
          </select>
          <button type="submit" disabled={selectedShelter?.status !== "active"}>
            建立帳號
          </button>
        </form>
      </section>

      <section aria-labelledby="area-list-title">
        <h2 id="area-list-title">Cage / Area</h2>
        <ul>
          {areas.map((area) => (
            <li key={area.id}>
              {area.name}（{area.area_type}／{area.status}）
            </li>
          ))}
        </ul>
        <form onSubmit={(event) => void submit(event, createArea)}>
          <label htmlFor="area-name">區域名稱</label>
          <input
            id="area-name"
            value={areaName}
            onChange={(event) => setAreaName(event.target.value)}
            required
          />
          <label htmlFor="area-type">類型</label>
          <select
            id="area-type"
            value={areaType}
            onChange={(event) =>
              setAreaType(event.target.value as Area["area_type"])
            }
          >
            <option value="area">Area</option>
            <option value="cage">Cage</option>
          </select>
          <button type="submit" disabled={selectedShelter?.status !== "active"}>
            建立區域
          </button>
        </form>
      </section>
    </main>
  );
}
