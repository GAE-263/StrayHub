// ============================================================
// 表單驗證小工具
// ============================================================

/**
 * 檢查「新增動物」表單是否可以送出。
 * 規則：一定要有照片 + 動物名稱(暱稱)不能空白。
 * 其他欄位(品種/年齡/地點/備註)算選填，收容現場常常資訊不齊全，
 * 不強制要求，避免志工卡在表單填不完就放棄使用。
 */
export function validateAddAnimalForm(draft) {
  const errors = [];
  if (!draft.photoFile) errors.push("請拍攝或上傳一張照片");
  if (draft.photoFile && draft.photoFile.size > 10 * 1024 * 1024) {
    errors.push("照片不可超過 10 MB");
  }
  if (
    draft.photoFile &&
    !["image/jpeg", "image/png", "image/webp"].includes(draft.photoFile.type)
  ) {
    errors.push("只支援 JPEG、PNG 或 WebP 圖片");
  }
  if (!draft.name || draft.name.trim() === "") errors.push("請輸入動物暱稱");
  return errors;
}

/**
 * 檢查「更新動物」表單是否可以送出。
 * 規則：一定要先查到有效的動物ID + 健康狀況描述不能空白。
 * 照片這裡算選填(有些更新單純只是補健康紀錄，不一定每次都要重拍照)。
 */
export function validateUpdateAnimalForm(draft) {
  const errors = [];
  if (!draft.matchedAnimal) errors.push("請先輸入動物ID並查詢");
  if (!draft.healthNotes || draft.healthNotes.trim() === "") {
    errors.push("請填寫健康狀況說明");
  }
  return errors;
}
