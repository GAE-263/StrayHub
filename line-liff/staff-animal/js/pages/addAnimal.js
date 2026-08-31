// ============================================================
// 「新增收容動物」流程邏輯
// 步驟：拍照/選圖 → (系統自動產生動物ID，一進畫面就顯示) → 填基礎資料 → 送出
// ============================================================

import { getState, setState, resetAddAnimalDraft } from "../state.js";
import { showScreen } from "../router.js";
import { submitNewAnimal } from "../api.js";
import { validateAddAnimalForm } from "../utils/validators.js";
import { setupPhotoPicker, resetPhotoPicker } from "../utils/camera.js";
import { renderMenuUserInfo } from "./menu.js";

const PHOTO_PICKER_IDS = {
  cameraInputId: "add-photo-camera-input",
  galleryInputId: "add-photo-gallery-input",
  previewImgId: "add-photo-preview",
  placeholderId: "add-photo-placeholder",
};

/**
 * 產生一組暫時動物ID，格式：A + 日期(YYYYMMDD) + 4碼隨機數字
 * 例如：A20260816-7431
 * 這只是「前端暫時編號」，方便志工現場核對、貼在籠子上等等；
 * 後端收到後可以直接沿用，或是換發正式的收容編號都可以，
 * 前端不假設後端一定會照用這組ID。
 */
function generateAnimalId() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  const rand = String(Math.floor(1000 + Math.random() * 9000));
  return `A${y}${m}${d}-${rand}`;
}

export function initAddAnimalPage() {
  setupPhotoPicker({
    ...PHOTO_PICKER_IDS,
    onPhotoSelected: (file) => {
      const draft = getState().addAnimalDraft;
      setState({ addAnimalDraft: { ...draft, photoFile: file } });
    },
  });

  // 表單欄位跟 state 同步：每個輸入框改變時，即時寫回 addAnimalDraft
  bindField("add-input-name", "name");
  bindField("add-input-species", "species");
  bindField("add-input-breed", "breed");
  bindField("add-input-gender", "gender");
  bindField("add-input-age", "estimatedAge");
  bindField("add-input-size", "size");
  bindField("add-input-location", "foundLocation");
  bindField("add-input-notes", "notes");

  document
    .getElementById("btn-add-animal-back")
    .addEventListener("click", () => {
      renderMenuUserInfo();
      showScreen("screen-menu");
    });

  document
    .getElementById("btn-add-animal-submit")
    .addEventListener("click", handleSubmit);
}

// 每次「進入」這個畫面時執行：產生新的動物ID、清空表單、重置照片預覽
export function onEnterAddAnimalPage() {
  resetAddAnimalDraft();
  const newId = generateAnimalId();
  setState({ addAnimalDraft: { ...getState().addAnimalDraft, animalId: newId } });
  document.getElementById("add-animal-id-display").textContent = newId;

  resetPhotoPicker(PHOTO_PICKER_IDS);
  document.getElementById("add-animal-form").reset();
  hideError();
}

function bindField(inputId, draftKey) {
  document.getElementById(inputId).addEventListener("input", (e) => {
    const draft = getState().addAnimalDraft;
    setState({ addAnimalDraft: { ...draft, [draftKey]: e.target.value } });
  });
}

async function handleSubmit() {
  const { addAnimalDraft, currentUser } = getState();
  const errors = validateAddAnimalForm(addAnimalDraft);

  if (errors.length > 0) {
    showError(errors.join("、"));
    return;
  }
  hideError();

  const submitBtn = document.getElementById("btn-add-animal-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "送出中...";

  try {
    await submitNewAnimal({
      currentUser,
      animalData: addAnimalDraft,
      photoFile: addAnimalDraft.photoFile,
    });
    alert(`新增成功！動物ID：${addAnimalDraft.animalId}`);
    renderMenuUserInfo();
    showScreen("screen-menu");
  } catch (err) {
    console.error(err);
    showError("送出失敗，請檢查網路連線後再試一次");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "送出";
  }
}

function showError(msg) {
  const box = document.getElementById("add-animal-error-box");
  box.textContent = msg;
  box.classList.remove("hidden");
}

function hideError() {
  document.getElementById("add-animal-error-box").classList.add("hidden");
}
