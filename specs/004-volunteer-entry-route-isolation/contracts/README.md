# Contract Index：志工角色導向入口與管理路由隔離

本功能只對既有 authentication contract 做一項 additive change：

- [liff-exchange.openapi.yaml](liff-exchange.openapi.yaml)：`POST /v1/auth/liff/exchange` request 新增必填 `shelter_entry_reference`；response 維持 canonical `AuthResponse`。
- [route-access.md](route-access.md)：正式 LIFF bootstrap、atomic exchange、登入目的地、route matrix、request ordering、current draft、401 recovery、LINE Bot regression 與 accessibility 行為。

實作時必須把 additive schema 合併至 `specs/001-volunteer-care-report/contracts/openapi.yaml`，再由 canonical 文件重新生成 `packages/contracts/src/openapi.ts`。不得只修改 generated TypeScript，也不得讓本目錄的 additive 文件成為第二份 production OpenAPI。

005 的 entry reference、Membership/Grant 與 authorization 邊界仍以 `specs/005-volunteer-access-approval/contracts/authorization.md` 為準；004 不重定義其 lifecycle。
