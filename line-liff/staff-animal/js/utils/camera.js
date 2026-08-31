// ============================================================
// 拍照 / 相簿選圖 共用邏輯
// 新增動物、更新動物兩個流程都需要「拍照或選相片 + 預覽」，抽出來共用。
//
// 做法說明：
//   手機瀏覽器(包含LINE內建瀏覽器)對 <input type="file" accept="image/*"> 的行為：
//     - 加上 capture="environment"：優先直接開啟後鏡頭相機
//     - 不加 capture：會跳出選單讓使用者選「拍照」或「從相簿選擇」
//   這裡兩個按鈕都提供，讓使用者可以自由選擇，UX比較彈性。
// ============================================================

/**
 * 幫指定的照片上傳區塊掛上事件，處理「選好照片後預覽 + 回呼」。
 *
 * @param {object} params
 * @param {string} params.cameraInputId   capture=environment 的 <input> id (拍照按鈕)
 * @param {string} params.galleryInputId  一般的 <input> id (從相簿選擇按鈕)
 * @param {string} params.previewImgId    預覽用的 <img> id
 * @param {string} params.placeholderId   還沒選照片時顯示的提示文字/圖示區塊 id
 * @param {(file: File) => void} params.onPhotoSelected  選好照片後的回呼，把 File 物件往上傳給頁面邏輯存起來
 */
export function setupPhotoPicker({
  cameraInputId,
  galleryInputId,
  previewImgId,
  placeholderId,
  onPhotoSelected,
}) {
  const allowedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
  const maxBytes = 10 * 1024 * 1024;
  const handleFile = (fileList) => {
    const file = fileList && fileList[0];
    if (!file) return;

    // 簡單防呆：確認選到的真的是圖片檔
    if (!allowedTypes.has(file.type)) {
      alert("只支援 JPEG、PNG 或 WebP 圖片");
      return;
    }
    if (file.size > maxBytes) {
      alert("照片不可超過 10 MB");
      return;
    }

    // 用 FileReader 讀成 DataURL 只是「為了畫面預覽」，
    // 真正要送給後端的還是 file 這個原始 File 物件(見 api.js 的 FormData 用法)，
    // 不要把預覽用的 Base64 字串跟要上傳的資料搞混。
    const reader = new FileReader();
    reader.onload = (e) => {
      const previewImg = document.getElementById(previewImgId);
      const placeholder = document.getElementById(placeholderId);
      previewImg.src = e.target.result;
      previewImg.classList.remove("hidden");
      if (placeholder) placeholder.classList.add("hidden");
    };
    reader.readAsDataURL(file);

    onPhotoSelected(file);
  };

  const cameraInput = document.getElementById(cameraInputId);
  const galleryInput = document.getElementById(galleryInputId);

  cameraInput.addEventListener("change", (e) => handleFile(e.target.files));
  galleryInput.addEventListener("change", (e) => handleFile(e.target.files));
}

/**
 * 重置照片選擇區塊回到「尚未選擇照片」的畫面狀態(送出成功、或切換到別的動物時使用)。
 */
export function resetPhotoPicker({
  cameraInputId,
  galleryInputId,
  previewImgId,
  placeholderId,
}) {
  document.getElementById(cameraInputId).value = "";
  document.getElementById(galleryInputId).value = "";
  const previewImg = document.getElementById(previewImgId);
  previewImg.src = "";
  previewImg.classList.add("hidden");
  const placeholder = document.getElementById(placeholderId);
  if (placeholder) placeholder.classList.remove("hidden");
}
