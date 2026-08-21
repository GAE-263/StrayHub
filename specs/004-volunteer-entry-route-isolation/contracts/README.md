# Contract Index：志工角色導向入口與管理路由隔離

本功能只對既有 authentication contract 做一項 additive change：

- [liff-exchange.openapi.yaml](liff-exchange.openapi.yaml)：`POST /v1/auth/liff/exchange` request 新增必填 `shelter_entry_reference`；response 維持 canonical `AuthResponse`。
- [route-access.md](route-access.md)：正式 LIFF bootstrap、atomic exchange、登入目的地、route matrix、request ordering、current draft、401 recovery、LINE Bot regression 與 accessibility 行為。

實作時必須把 additive schema 合併至 `specs/001-volunteer-care-report/contracts/openapi.yaml`，再由 canonical 文件重新生成 `packages/contracts/src/openapi.ts`。不得只修改 generated TypeScript，也不得讓本目錄的 additive 文件成為第二份 production OpenAPI。

005 的 entry reference、Membership/Grant 與 authorization 邊界仍以 `specs/005-volunteer-access-approval/contracts/authorization.md` 為準；004 不重定義其 lifecycle。

## Operational LIFF／tunnel handoff

正式手機驗收的可執行步驟與遮罩後 evidence schema 位於：

- [`../quickstart.md`](../quickstart.md) §11：local services、兩條HTTPS tunnel、LIFF Console、Rich Menu dry-run與Case A–D入口。
- [`../validation/controlled-line-evidence.md`](../validation/controlled-line-evidence.md)：受控LINE／LIFF驗收的完整操作與證據模板。

Runtime environment mapping：

| Variable                  | Consumer                                    | Contract                                                    |
| ------------------------- | ------------------------------------------- | ----------------------------------------------------------- |
| `LIFF_ID`                 | Next.js `/volunteer-entry` Server Component | LIFF Console中的LIFF ID；啟動時讀取                         |
| `API_BASE_URL`            | Next.js `/v1/[...path]` server proxy        | API HTTPS origin；不可為localhost、空值或HTTP               |
| `LIFF_BASE_URL`           | Rich Menu validation script                 | `https://liff.line.me/<LIFF_ID>`；不可帶path/query/fragment |
| `SHELTER_ENTRY_REFERENCE` | Rich Menu rendering／受控handoff            | 32–512字元opaque reference；只短暫存在受控shell             |
| `LINE_LOGIN_CHANNEL_ID`   | FastAPI LINE identity verifier              | 必須與LIFF App所屬LINE Login channel audience一致           |

`NEXT_PUBLIC_LIFF_ID`與`NEXT_PUBLIC_API_BASE_URL`不是正式volunteer entry runtime的source of truth。任何raw ID token、raw entry reference、LINE user ID、Secret或protected data都不屬於本contract evidence。
