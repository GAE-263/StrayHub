# Contract Index：志工角色導向入口與管理路由隔離

本功能不修改 OpenAPI、CRM schema 或後端 authorization contract。以下文件定義既有介面在前端 route composition 中必須呈現的可觀察行為：

- [route-access.md](route-access.md)：登入目的地、角色推導、管理／志工 route matrix、request ordering、active draft 恢復、錯誤與 accessibility contract。

正式 HTTP contract 仍以 `specs/001-volunteer-care-report/contracts/openapi.yaml` 為唯一來源；`packages/contracts/src/openapi.ts` 仍由該檔生成，不得手動修改。
