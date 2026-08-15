# Contract Index：志工報名與限時授權

本目錄定義 005 新增的 API 與 authorization 邊界：

- [volunteer-access.openapi.yaml](volunteer-access.openapi.yaml)：LIFF 報名／狀態／撤回、organization policy、顯式或 all-filtered target snapshot、批次進度／逐筆結果、限時 Grant、統一通知失敗清單、單筆／多筆重試與 PLATFORM_ADMIN 支援原因的 additive HTTP contract。
- [authorization.md](authorization.md)：effective Membership、資料可見性、租戶 scope、PLATFORM_ADMIN target/reason/read-write Audit、Session/context 失效、全選快照／分段交易、通知 outbox 與 004 整合規則。

## Canonical OpenAPI 整合

本目錄的 OpenAPI 是規劃階段可獨立審查的 additive contract。實作時必須把 paths、schemas 與 error semantics 合併至專案 canonical source：

```text
specs/001-volunteer-care-report/contracts/openapi.yaml
```

接著重新生成：

```bash
npm --prefix packages/contracts run generate
npm --prefix packages/contracts run check
```

不得手動修改 `packages/contracts/src/openapi.ts` 來繞過 canonical contract。

## 版本與相容性

- 所有新增 endpoint 都是 additive；既有 credential login、LINE bind、care report 與 management endpoint 不移除。
- `OrganizationMembership` response 會 additive 增加 `valid_from`、`expires_at`、`access_version`；管理角色可為 null，VOLUNTEER 必須有值。
- 004 的 `POST /v1/auth/liff/exchange` 後續加入同型別 `shelter_entry_reference`，並使用 [authorization.md](authorization.md) 的 effective Membership predicate；005 本身不在 pending application 階段建立一般 Session/context。
- `X-Platform-Support-Reason` 對 SHELTER_ADMIN 可省略；PLATFORM_ADMIN 呼叫本功能任何 organization-scoped read/write 時必填，且不得用來請求混合 organization 清單。
- 日期時間以 RFC 3339 UTC 傳輸；UI 負責轉為台灣時區。
