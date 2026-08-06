# OpenAPI Contract Types 契約

## 唯一來源

`specs/001-volunteer-care-report/contracts/openapi.yaml` 是本 Feature HTTP API 的唯一正式 Contract。`packages/contracts/src/openapi.ts` 是由 `openapi-typescript` 產生的 type-only 衍生檔，不得手動修改，也不得反向覆蓋 OpenAPI。

## 產生與驗證

`packages/contracts/package.json` 必須提供：

- `generate`：由 Feature OpenAPI 重新產生 `src/openapi.ts`。
- `check`：重新產生至暫存位置並比對已提交型別；有差異時失敗。

標準驗證命令為：

```bash
npm --prefix packages/contracts run generate
npm --prefix packages/contracts run check
```

`apps/web` 的 API client 必須引用此 package 的型別，不得在各 Feature 內手動複製 Request／Response interface。生成型別不包含 Authorization Policy、Domain Rule 或 Runtime Validation。

## 後端邊界

FastAPI 的 Pydantic Request／Response Model 維持獨立，不能由 TypeScript 生成檔反向產生。`tests/contract/test_openapi_contract.py` 與 endpoint contract tests 必須驗證：

- OpenAPI 可解析且必要路徑存在。
- Pydantic 實際 Request／Response 符合 OpenAPI。
- 受保護 endpoint 具有正確 Authentication requirement。
- 生成型別與 OpenAPI 無漂移。
- 一般 Organization request 不得以 `org_id` 取代 Session 的 Active Shelter Context。

## 版本與失敗規則

`openapi-typescript` 版本固定於 `packages/contracts/package.json` 及 lockfile。OpenAPI 或 generator 版本變更後必須重新產生並審查差異；CI 中的 `check` 失敗時不得以手動修改生成檔處理。
