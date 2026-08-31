// 由 infra/local/line-rich-menu-*.yaml 產生 2500x1686 的占位底圖。
//
// 這套工具原本沒有進版控，底圖只能手工重畫。改選單項目時請跑：
//   node scripts/rich_menu_images/render.mjs
// 產出會覆蓋 infra/local/rich-menu-images/<role>.png。
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
// playwright 只裝在 apps/web；這支腳本不在它底下，Node 的 node_modules
// 往上找不到，所以明確指出位置。
const { chromium } = createRequire(import.meta.url)(
  join(ROOT, "apps/web/node_modules/playwright"),
);
const CONFIG_DIR = join(ROOT, "infra/local");
const OUT_DIR = join(ROOT, "infra/local/rich-menu-images");
const WIDTH = 2500;
const HEIGHT = 1686;

// 極簡 YAML 讀取：只支援本專案這幾份選單檔的固定結構。
function parseMenu(text) {
  const doc = { actions: [] };
  let current = null;
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim() || line.trim().startsWith("#")) continue;
    const item = line.match(/^\s*-\s*(\w+):\s*(.*)$/);
    if (item) {
      current = { [item[1]]: item[2] };
      doc.actions.push(current);
      continue;
    }
    const nested = line.match(/^\s{4,}(\w+):\s*(.*)$/);
    if (nested && current) {
      current[nested[1]] = nested[2];
      continue;
    }
    const top = line.match(/^(\w+):\s*(.*)$/);
    if (top && top[2]) doc[top[1]] = top[2];
  }
  return doc;
}

const EMOJI = {
  start_volunteer_application: "🐾",
  adoption_placeholder: "🏡",
  shelter_info: "🏠",
  start_binding: "🤝",
  walk_report: "🚶",
  volunteer_checkin: "📋",
  want_to_adopt: "🐶",
  adoption_report: "💌",
  staff_create_animal: "➕",
  staff_update_health: "🩺",
  staff_animal_list: "📖",
  staff_change_status: "🔄",
  back_to_default_menu: "↩️",
};

const ROLE_TITLE = {
  default: "預設選單",
  volunteer: "志工選單",
  adopter: "領養人選單",
  staff: "工作人員選單",
};

function html(doc, role) {
  const cards = doc.actions
    .map((action, index) => {
      const code = (action.data || "").replace(/^action=/, "");
      return `<div class="card">
        <div class="num">${index + 1}</div><div class="spark">🌟</div>
        <div class="mid"><div class="emoji">${EMOJI[code] || "✨"}</div>
        <div class="label">${action.label}</div></div>
        <div class="code">action=${code}</div>
      </div>`;
    })
    .join("");
  return `<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@500;700;900&display=swap');
  *{box-sizing:border-box;margin:0}
  body{width:${WIDTH}px;height:${HEIGHT}px;background:#FAF6EE;
    background-image:radial-gradient(#E9DFCC 3px,transparent 3px);background-size:60px 60px;
    font-family:'Noto Sans TC','Apple Color Emoji',sans-serif;color:#716053;
    padding:56px;display:flex;flex-direction:column;gap:28px}
  .bar{background:#F0DFC4;border:9px solid #716053;border-radius:44px;padding:26px 44px;
    display:flex;align-items:center;justify-content:space-between}
  .bar h1{font-size:76px;font-weight:900}
  .chat{background:#FFFDF8;border:7px solid #716053;border-radius:999px;
    padding:14px 34px;font-size:44px;font-weight:700}
  .row{flex:1;display:flex;gap:36px}
  .card{flex:1;position:relative;background:#F8E9D2;border:9px solid #716053;border-radius:52px;
    box-shadow:14px 14px 0 #D9C5A6;display:flex;flex-direction:column;
    align-items:center;justify-content:center;padding:44px}
  .num{position:absolute;top:36px;left:40px;width:82px;height:82px;border:6px solid #716053;
    border-radius:50%;display:flex;align-items:center;justify-content:center;
    font-size:46px;font-weight:900;background:#FFFDF8}
  .spark{position:absolute;top:34px;right:40px;font-size:64px}
  .mid{display:flex;flex-direction:column;align-items:center;gap:26px}
  .emoji{font-size:${doc.actions.length > 2 ? 130 : 190}px;line-height:1}
  .label{font-size:${doc.actions.length > 2 ? 68 : 104}px;font-weight:900;text-align:center;
    line-height:1.25;word-break:break-word}
  .code{position:absolute;bottom:34px;left:32px;right:32px;text-align:center;
    font-family:ui-monospace,monospace;font-size:${doc.actions.length > 2 ? 26 : 32}px;
    color:#A2917F;word-break:break-all}
  .foot{display:flex;justify-content:space-between;font-size:40px;font-weight:700}
  </style>
  <div class="bar"><h1>🐾 ${ROLE_TITLE[role] || role}</h1>
    <div class="chat">聊天列：${doc.chatBarText} 🎈</div></div>
  <div class="row">${cards}</div>
  <div class="foot"><div>🌟 ${role}.png · ${WIDTH} × ${HEIGHT} · ${doc.actions.length} 區</div>
    <div>占位底圖，之後可換正式插畫</div></div>`;
}

// PLAYWRIGHT_CHROMIUM_PATH 可指向已安裝的 Chromium，省去為了產圖再下載一份
// （apps/web 的 playwright 版本與快取內的 build 未必相同）。
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
const browser = await chromium.launch(executablePath ? { executablePath } : {});
const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT } });
for (const file of readdirSync(CONFIG_DIR).filter((f) => /^line-rich-menu-.*\.yaml$/.test(f))) {
  const doc = parseMenu(readFileSync(join(CONFIG_DIR, file), "utf8"));
  const role = doc.role;
  await page.setContent(html(doc, role));
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: join(OUT_DIR, `${role}.png`) });
  console.log(`[OK] ${role}.png（${doc.actions.length} 區）`);
}
await browser.close();
