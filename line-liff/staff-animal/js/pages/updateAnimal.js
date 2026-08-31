// ============================================================
// 「更新現有動物紀錄」流程邏輯
// 步驟：輸入動物ID查詢 → 確認查到的動物 → 拍照/選圖(選填) → 填健康狀況 → 送出
// ============================================================

import { getState, setState, resetUpdateAnimalDraft } from "../state.js";
import { showScreen } from "../router.js";
import { lookupAnimalById, submitAnimalHealthUpdate } from "../api.js";
import { validateUpdateAnimalForm } from "../utils/validators.js";
import { setupPhotoPicker, resetPhotoPicker } from "../utils/camera.js";
import { renderMenuUserInfo } from "./menu.js";

const PHOTO_PICKER_IDS = {
  cameraInputId: "update-photo-camera-input",
  galleryInputId: "update-photo-gallery-input",
  previewImgId: "update-photo-preview",
  placeholderId: "update-photo-placeholder",
};

export function initUpdateAnimalPage() {
  setupPhotoPicker({
    ...PHOTO_PICKER_IDS,
    onPhotoSelected: (file) => {
      const draft = getState().updateAnimalDraft;
      setState({ updateAnimalDraft: { ...draft, photoFile: file } });
    },
  });

  document
    .getElementById("btn-lookup-animal")
    .addEventListener("click", handleLookup);

  document
    .getElementById("update-input-animal-id")
    .addEventListener("input", (e) => {
      const draft = getState().updateAnimalDraft;
      // 使用者一改動ID輸入框，之前查到的結果就先清掉，避免誤送到舊的動物身上
      setState({
        updateAnimalDraft: { ...draft, animalId: e.target.value, matchedAnimal: null },
      });
      document.getElementById("update-matched-animal-box").classList.add("hidden");
      document.getElementById("update-detail-section").classList.add("hidden");
    });

  document
    .getElementById("update-input-health-status")
    .addEventListener("change", (e) => {
      const draft = getState().updateAnimalDraft;
      setState({ updateAnimalDraft: { ...draft, healthStatus: e.target.value } });
    });

  document
    .getElementById("update-input-health-notes")
    .addEventListener("input", (e) => {
      const draft = getState().updateAnimalDraft;
      setState({ updateAnimalDraft: { ...draft, healthNotes: e.target.value } });
    });

  document
    .getElementById("btn-update-animal-back")
    .addEventListener("click", () => {
      renderMenuUserInfo();
      showScreen("screen-menu");
    });

  document
    .getElementById("btn-update-animal-submit")
    .addEventListener("click", handleSubmit);
}

export function onEnterUpdateAnimalPage() {
  resetUpdateAnimalDraft();
  document.getElementById("update-input-animal-id").value = "";
  document.getElementById("update-matched-animal-box").classList.add("hidden");
  document.getElementById("update-detail-section").classList.add("hidden");
  resetPhotoPicker(PHOTO_PICKER_IDS);
  document.getElementById("update-animal-form").reset();
  hideError();
}

async function handleLookup() {
  const animalId = document.getElementById("update-input-animal-id").value.trim();
  if (!animalId) {
    showError("請先輸入動物ID");
    return;
  }
  hideError();

  const lookupBtn = document.getElementById("btn-lookup-animal");
  lookupBtn.disabled = true;
  lookupBtn.textContent = "查詢中...";

  try {
    const animal = await lookupAnimalById(animalId);

    if (!animal) {
      showError("查無此動物ID，請確認後再輸入一次");
      document.getElementById("update-matched-animal-box").classList.add("hidden");
      document.getElementById("update-detail-section").classList.add("hidden");
      return;
    }

    const draft = getState().updateAnimalDraft;
    setState({
      updateAnimalDraft: { ...draft, animalId, matchedAnimal: animal },
    });

    // 顯示查到的動物基本資料，讓使用者「肉眼確認」是不是要更新的那隻，
    // 避免ID打錯字卻沒發現、健康紀錄記到別隻動物身上這種現場最容易出的錯。
    document.getElementById("update-matched-animal-name").textContent = animal.name;
    document.getElementById("update-matched-animal-id").textContent = animal.animalId;
    document.getElementById("update-matched-animal-photo").src = animal.photoUrl;
    document.getElementById("update-matched-animal-box").classList.remove("hidden");
    document.getElementById("update-detail-section").classList.remove("hidden");
  } catch (err) {
    console.error(err);
    showError("查詢失敗，請檢查網路連線後再試一次");
  } finally {
    lookupBtn.disabled = false;
    lookupBtn.textContent = "查詢";
  }
}

async function handleSubmit() {
  const { updateAnimalDraft, currentUser } = getState();
  const errors = validateUpdateAnimalForm(updateAnimalDraft);

  if (errors.length > 0) {
    showError(errors.join("、"));
    return;
  }
  hideError();

  const submitBtn = document.getElementById("btn-update-animal-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "送出中...";

  try {
    await submitAnimalHealthUpdate({
      currentUser,
      animalId: updateAnimalDraft.animalId,
      healthData: {
        status: updateAnimalDraft.healthStatus,
        description: updateAnimalDraft.healthNotes,
      },
      photoFile: updateAnimalDraft.photoFile,
    });
    alert(`健康紀錄更新成功！動物ID：${updateAnimalDraft.animalId}`);
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
  const box = document.getElementById("update-animal-error-box");
  box.textContent = msg;
  box.classList.remove("hidden");
}

function hideError() {
  document.getElementById("update-animal-error-box").classList.add("hidden");
}
