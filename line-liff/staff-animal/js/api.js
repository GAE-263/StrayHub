// ============================================================
// StrayHub 工作人員動物輸入 — 後端 API 合約
// 這支檔案是「LINE 介面 ↔ StrayHub 後端」的合約。後端只要看這支，
// 就知道每個功能會打哪個路徑、帶什麼資料、預期拿到什麼。
//
// 重要：StrayHub 目前「尚未」提供『建立動物』端點（management_animals
// 只有列表 / 查詢 / 改狀態）。下方標 [後端待實作] 的端點需要後端補上；
// 參數/回傳已照真實情境設計好，接上後前端頁面不用再改。
//
// 切換：USE_MOCK_API=true 用假資料；false 真的打 CONFIG.API_BASE_URL。
// ============================================================

import { CONFIG } from "./config.js";

const USE_MOCK_API = true; // [接後端時要改] 後端就緒後改成 false

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
export async function verifyUserRole(lineProfile) {
  if (USE_MOCK_API) {
    await mockDelay();
    return {
      lineUserId: lineProfile.userId,
      displayName: lineProfile.displayName,
      pictureUrl: lineProfile.pictureUrl,
      role: "staff", // 本 LIFF 為工作人員用，模擬固定回傳 staff
    };
  }
  // [後端對接] StrayHub：POST /v1/line/bind（帶 id_token），回傳含角色/收容所。
  const res = await fetch(`${CONFIG.API_BASE_URL}/line/bind`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lineUserId: lineProfile.userId }),
  });
  return handleJson(res, "身分驗證失敗");
}

// ------------------------------------------------------------
// 2. 依動物 ID / 收容編號查詢（更新流程用，讓工作人員確認是不是要更新的那隻）
// ------------------------------------------------------------
export async function lookupAnimalById(animalId) {
  if (USE_MOCK_API) {
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
  const res = await fetch(
    `${CONFIG.API_BASE_URL}/management/animals/${encodeURIComponent(animalId)}`
  );
  if (res.status === 404) return null;
  return handleJson(res, "查詢動物資料失敗");
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
      lineUserId: currentUser.lineUserId,
      displayName: currentUser.displayName,
      role: currentUser.role, // staff
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

  if (USE_MOCK_API) {
    console.log("[模擬送出] 新增動物 payload:", payload);
    console.log("[模擬送出] 附帶照片:", photoFile);
    await mockDelay(800);
    return { success: true, animalId: animalData.animalId };
  }

  // [後端待實作] StrayHub 目前沒有此端點，需後端補上。
  const formData = new FormData();
  formData.append("payload", JSON.stringify(payload));
  formData.append(CONFIG.PHOTO_FIELD_NAME, photoFile, photoFile.name);
  const res = await fetch(`${CONFIG.API_BASE_URL}/management/animals`, {
    method: "POST",
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
      lineUserId: currentUser.lineUserId,
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

  if (USE_MOCK_API) {
    console.log("[模擬送出] 更新健康紀錄 payload:", payload);
    console.log("[模擬送出] 附帶照片:", photoFile);
    await mockDelay(800);
    return { success: true };
  }

  // [後端待實作]
  const formData = new FormData();
  formData.append("payload", JSON.stringify(payload));
  if (photoFile) formData.append(CONFIG.PHOTO_FIELD_NAME, photoFile, photoFile.name);
  const res = await fetch(
    `${CONFIG.API_BASE_URL}/management/animals/${encodeURIComponent(animalId)}/health-records`,
    { method: "POST", body: formData }
  );
  return handleJson(res, "送出失敗，請稍後再試");
}

function mockDelay(ms = 500) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
