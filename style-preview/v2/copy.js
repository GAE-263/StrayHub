// 由 copy.yaml 產生，不要直接改這個檔案。
// 改文案請編輯 copy.yaml，然後執行：python build_preview.py
window.COPY = {
  "menu": {
    "start": {
      "label": "開始散步回報",
      "sub": "",
      "glyph": "🐾"
    },
    "resume": {
      "label": "繼續回報",
      "sub": "",
      "glyph": "▶"
    },
    "contact": {
      "label": "聯絡工作人員",
      "sub": "",
      "glyph": "💬"
    }
  },
  "resume_empty": {
    "glyph": "📭",
    "caption": "散步回報",
    "title": "目前沒有未完成的回報",
    "body": "按「開始散步回報」就可以挑一隻毛孩了 🐾"
  },
  "contact": {
    "glyph": "💬",
    "caption": "聯絡",
    "title": "請直接聯繫工作人員",
    "body": "A 區犬舍 · 分機 214，或在群組留言。"
  },
  "find_dog": {
    "glyph": "🔎",
    "caption": "散步回報",
    "title": "要幫哪隻毛孩回報",
    "qr": "掃描 QR 貼紙",
    "search": "輸入編號或名字",
    "list": "看今日名單"
  },
  "qr_scan": {
    "glyph": "📷",
    "caption": "散步回報",
    "title": "掃描籠舍上的 QR 貼紙",
    "body": "點下面的 📷 相機，對準 QR 貼紙拍下去就好。 貼紙壞了或找不到，可以改用輸入搜尋。",
    "waiting": "等你掃描 QR…",
    "found": "掃到了，是 {dog}",
    "switch_to_search": "改用輸入搜尋"
  },
  "search": {
    "glyph": "🔤",
    "caption": "散步回報",
    "title": "輸入編號或名字",
    "body": "直接在下面輸入框打幾個字就好，例如「財」或收容編號後幾碼，不用打全名。",
    "placeholder": "輸入編號或名字…",
    "no_result": "找不到符合「{query}」的毛孩，換個關鍵字試試 🔍",
    "multi_result": "符合「{query}」的有 {count} 隻，請選一隻："
  },
  "overview": {
    "glyph": "📋",
    "caption": "今天已完成 {done} / {total}",
    "title": "今日散步進度",
    "footer": "點一隻毛孩就可以開始回報 🐾",
    "status_done": "已回報 · {time}",
    "status_pending": "尚未散步"
  },
  "confirm": {
    "glyph": "🐶",
    "caption": "{shelter_no}　所在區域：A 區犬舍",
    "title": "是 {dog} 嗎？",
    "accept": "確認是這隻",
    "reject": "換一隻",
    "after": "已建立草稿"
  },
  "questions_caption": "散步回報 · 第 {n} / {all} 題",
  "questions_footer": "點錯了可以退回上一題，沒觀察到就按「今天沒觀察到這項」🍃",
  "questions_back": "上一步",
  "skip_label": "今天沒觀察到這項",
  "skip_glyph": "👀",
  "questions": [
    {
      "key": "walk_completion",
      "icon": "🚶",
      "title": "散步完成",
      "options": [
        [
          "有走完",
          "✅"
        ],
        [
          "走一半",
          "🌤"
        ],
        [
          "沒走成(懶散不走)",
          "🚫"
        ]
      ]
    },
    {
      "key": "energy",
      "icon": "⚡",
      "title": "精神體力",
      "options": [
        [
          "比平常好",
          "⬆️"
        ],
        [
          "跟平常一樣",
          "➡️"
        ],
        [
          "比平常差",
          "⬇️"
        ]
      ]
    },
    {
      "key": "gait",
      "icon": "🐾",
      "title": "走路姿勢",
      "options": [
        [
          "正常",
          "✅"
        ],
        [
          "有點怪",
          "🤔"
        ],
        [
          "明顯不對",
          "⚠️"
        ]
      ]
    },
    {
      "key": "defecation",
      "icon": "💩",
      "title": "大便",
      "stool_photo_unless": "沒排便",
      "options": [
        [
          "正常",
          "✅"
        ],
        [
          "偏軟",
          "🌀"
        ],
        [
          "沒排便",
          "➖"
        ],
        [
          "有異狀",
          "⚠️"
        ]
      ]
    },
    {
      "key": "dog_interaction",
      "icon": "🐕",
      "title": "對其他狗",
      "options": [
        [
          "友善",
          "🙂"
        ],
        [
          "沒反應",
          "😐"
        ],
        [
          "緊張或想衝",
          "😬"
        ],
        [
          "路上沒遇到",
          "➖"
        ]
      ]
    },
    {
      "key": "appearance",
      "icon": "🔍",
      "title": "身體外觀",
      "options": [
        [
          "沒發現異狀",
          "✅"
        ],
        [
          "皮膚或毛髮異常",
          "🩹"
        ],
        [
          "傷口或紅腫",
          "⚠️"
        ],
        [
          "其他",
          "✏️"
        ]
      ]
    }
  ],
  "stool_photo": {
    "glyph": "🔬",
    "caption": "大便：{value} · 有拍最好",
    "title": "拍一張便便照片",
    "body": "點聊天室下面的 📷 相機 或 🖼 相簿 直接傳過來就好。\n旁邊放個東西當比例尺會更準 📏",
    "skip": "這次略過",
    "footer": "這張只給照護判讀用，不會出現在對外的貼文 🔒",
    "waiting": "等你傳便便照片…",
    "received": "收到便便照片了，謝謝 🙌"
  },
  "portrait_photo": {
    "glyph": "📸",
    "caption": "散步回報 · 選填",
    "title": "拍一張今天的牠",
    "body": "一樣點下面的 📷 相機 或 🖼 相簿 傳過來，想傳幾張都行。\n這張之後可能會用在幫牠找家的貼文上 💛",
    "skip": "沒拍到，略過",
    "back": "上一步",
    "waiting": "等你傳狗狗照片…",
    "received": "收到照片了，好可愛 🥰"
  },
  "note": {
    "glyph": "💭",
    "caption": "散步回報 · 選填",
    "title": "健康或行為上想補充的",
    "body": "身體或行為上有想講的，直接打字傳過來。例如左後腳好像不太敢踩。",
    "skip": "沒有要補充的",
    "back": "上一步"
  },
  "story": {
    "glyph": "✨",
    "caption": "散步回報 · 選填",
    "title": "今天有發生什麼有趣的事嗎",
    "body": "追蝴蝶、賴在草地上不走、跟誰變成好朋友都算 🐾\n這些會變成之後幫牠找家的小故事。",
    "skip": "今天沒什麼特別的",
    "back": "上一步"
  },
  "summary": {
    "glyph": "📋",
    "caption": "{dog} · 送出前還可以修改",
    "title": "回報摘要",
    "submit": "送出回報",
    "edit": "再改一下",
    "switch": "換一隻",
    "unobserved": "—　未觀察"
  },
  "done": {
    "glyph": "🎉",
    "caption": "辛苦了，謝謝你 💚",
    "title": "回報完成",
    "body": "陪 {dog} 的紀錄已經收好了 🌟",
    "sub": "AI 分析會在背景進行，不影響這筆紀錄。",
    "footer": "下次要回報，再按一次選單就好 🐾"
  },
  "demo_dogs": [
    {
      "name": "小黑",
      "shelter_no": "VAAAG114080610",
      "done": null
    },
    {
      "name": "大黑",
      "shelter_no": "VAAAG114080699",
      "done": null
    },
    {
      "name": "阿財",
      "shelter_no": "VAAAG114080611",
      "done": "09:12"
    },
    {
      "name": "大寶",
      "shelter_no": "VAAAG114080612",
      "done": null
    },
    {
      "name": "咪咪",
      "shelter_no": "VAAAG114080613",
      "done": "08:40"
    }
  ],
  "tones": {
    "find_dog": "butter",
    "qr_scan": "sky",
    "search": "lilac",
    "overview": "leaf",
    "confirm": "butter",
    "question": "butter",
    "stool_photo": "peach",
    "portrait_photo": "sky",
    "note": "lilac",
    "story": "butter",
    "summary": "peach",
    "done": "leaf",
    "resume_empty": "peach",
    "contact": "sky"
  },
  "glyphs": {
    "skip": "⏭",
    "back": "←",
    "confirm": "✅",
    "switch": "🔄",
    "edit": "✏️",
    "dog_done": "✅",
    "dog_pending": "🐕"
  },
  "steps": {
    "find_dog": "找動物",
    "qr_scan": "掃描 QR",
    "search": "文字搜尋",
    "pick_animal": "選擇動物",
    "confirm_animal": "確認動物",
    "question": "第 {n} 題",
    "stool_photo": "便便照片",
    "stool_skipped": "便便照片（略過）",
    "portrait": "照片",
    "note": "觀察補充",
    "story": "小故事",
    "summary": "摘要",
    "send_photo": "傳送照片",
    "done": "完成"
  }
};
