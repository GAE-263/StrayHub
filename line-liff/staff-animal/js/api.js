// ============================================================
// StrayHub 工作人員動物輸入 — 後端 API 合約
// 這支檔案是「LINE 介面 ↔ StrayHub 後端」的合約。後端只要看這支，
// 就知道每個功能會打哪個路徑、帶什麼資料、預期拿到什麼。
//
// 身分與 shelter scope 一律由後端 session 決定；payload 不傳 organizationId。
// ============================================================

import { CONFIG } from "./config.js";

let accessToken = null;

function authHeaders() {
  if (!accessToken) throw new Error("尚未完成工作人員身分驗證");
  return { Authorization: `Bearer ${accessToken}` };
}

async function handleJson(res, errorMessage) {
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body?.message || body?.error || "";
    } catch (_) {}
    throw new Error(detail || errorMessage);
  }
  return res.json();
}

// ------------------------------------------------------------
// 1. 確認登入者身分（工作人員）
//    正式流程：LIFF 取得 id_token → 後端 POST /v1/line/bind 綁定並回傳
//    session 與角色。這裡沿用「回傳角色」的介面，工作人員角色才可用本 LIFF。
// ------------------------------------------------------------
export async function verifyUserRole({ profile, idToken }) {
  if (CONFIG.MOCK_MODE) {
    await mockDelay();
    accessToken = "local-memory-only-token";
    return {
      displayName: profile.displayName,
      pictureUrl: profile.pictureUrl,
      role: "STAFF",
      organizationId: "local-mock-organization",
    };
  }
  // LINE userId 只供 UI 顯示；後端只驗證 LINE 簽發的 id_token。
  const res = await fetch(`${CONFIG.API_BASE_URL}/line/bind`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: idToken }),
  });
  const session = await handleJson(res, "身分驗證失敗或尚未選定收容所");
  accessToken = session.access_token;
  const me = await fetch(`${CONFIG.API_BASE_URL}/auth/me`, { headers: authHeaders() });
  const identity = await handleJson(me, "無法確認工作人員權限");
  const membership = identity.memberships.find((item) =>
    ["STAFF", "SHELTER_ADMIN"].includes(item.role)
  );
  if (!membership) {
    accessToken = null;
    throw new Error("此帳號沒有目前收容所的工作人員權限");
  }
  return {
    displayName: identity.user.display_name || profile.displayName,
    pictureUrl: profile.pictureUrl,
    role: membership.role,
    organizationId: membership.organization_id,
  };
}

// ------------------------------------------------------------
// 2. 依動物 ID / 收容編號查詢（更新流程用，讓工作人員確認是不是要更新的那隻）
// ------------------------------------------------------------
export async function lookupAnimalById(animalId) {
  if (CONFIG.MOCK_MODE) {
    await mockDelay();
    if (!animalId || animalId.trim() === "") return null;
    return {
      animalId: animalId.trim(),
      name: "小黑",
      species: "dog",
      photoUrl: "https://placehold.co/300x300?text=" + encodeURIComponent(animalId),
    };
  }
  // StrayHub：GET /v1/management/animals/{animalId}（require_staff_or_admin）
  const res = await fetch(`${CONFIG.API_BASE_URL}/management/animals/${encodeURIComponent(animalId)}`, {
    headers: authHeaders(),
  });
  if (res.status === 404) return null;
  const body = await handleJson(res, "查詢動物資料失敗");
  return body.animal;
}

// ------------------------------------------------------------
// 3. 新增收容動物  [後端待實作]
//    期望端點：POST /v1/management/animals（multipart/form-data）
//    - payload 欄位：JSON 字串（見下方）
//    - photo 欄位：照片檔案
// ------------------------------------------------------------
export async function submitNewAnimal({ currentUser, animalData, photoFile }) {
  const payload = {
    requestType: "CREATE_ANIMAL",
    submittedBy: {
      displayName: currentUser.displayName,
      role: currentUser.role,
    },
    animal: {
      tempAnimalId: animalData.animalId,
      name: animalData.name,
      species: animalData.species,
      breed: animalData.breed,
      gender: animalData.gender,
      estimatedAge: animalData.estimatedAge,
      size: animalData.size,
      foundLocation: animalData.foundLocation,
      notes: animalData.notes,
    },
    submittedAt: new Date().toISOString(),
  };

  if (CONFIG.MOCK_MODE) {
    console.log("[模擬送出] 新增動物 payload:", payload);
    console.log("[模擬送出] 附帶照片:", photoFile);
    await mockDelay(800);
    return { success: true, animalId: animalData.animalId };
  }

  const formData = new FormData();
  formData.append("payload", JSON.stringify(payload));
  formData.append(CONFIG.PHOTO_FIELD_NAME, photoFile, photoFile.name);
  const res = await fetch(`${CONFIG.API_BASE_URL}/management/animals`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  return handleJson(res, "送出失敗，請稍後再試");
}

// ------------------------------------------------------------
// 4. 更新動物健康紀錄  [後端待實作]
//    期望端點：POST /v1/management/animals/{animalId}/health-records
// ------------------------------------------------------------
export async function submitAnimalHealthUpdate({ currentUser, animalId, healthData, photoFile }) {
  const payload = {
    requestType: "UPDATE_ANIMAL_HEALTH",
    submittedBy: {
      displayName: currentUser.displayName,
      role: currentUser.role,
    },
    animalId: animalId,
    healthRecord: {
      status: healthData.status,
      description: healthData.description,
    },
    submittedAt: new Date().toISOString(),
  };

  if (CONFIG.MOCK_MODE) {
    console.log("[模擬送出] 更新健康紀錄 payload:", payload);
    console.log("[模擬送出] 附帶照片:", photoFile);
    await mockDelay(800);
    return { success: true };
  }

  const formData = new FormData();
  formData.append("payload", JSON.stringify(payload));
  if (photoFile) formData.append(CONFIG.PHOTO_FIELD_NAME, photoFile, photoFile.name);
  const res = await fetch(
    `${CONFIG.API_BASE_URL}/management/animals/${encodeURIComponent(animalId)}/health-records`,
    { method: "POST", headers: authHeaders(), body: formData }
  );
  return handleJson(res, "送出失敗，請稍後再試");
}

function mockDelay(ms = 500) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
