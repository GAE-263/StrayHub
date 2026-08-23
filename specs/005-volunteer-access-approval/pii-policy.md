# 志工申請個人資料政策

## 狀態與範圍

本文件是 Hub／legacy entry 共用的志工申請 PII 儲存、揭露、稽核、保存與金鑰政策。它適用於姓名、手機、基本申請資料，以及收容所保險流程條件式要求的身分證字號。

本文件定義產品與資安預設值；台灣個人資料保護法的適用版本、特定保險契約及合作收容所的法定保存義務仍須由正式法遵確認。法遵 override 必須記錄依據、範圍、到期日與核准人，不能轉成無限期保存。

## 核心不變量

1. Client 選擇 `organization_id` 或提供 entry reference 只決定申請 target，不授予 Membership、Grant、PII read 或 CRM 權限。
2. 姓名、手機、身分證字號不得以 plaintext 寫入 PostgreSQL、Audit、log、exception、URL、client authorization state、snapshot 或測試 fixture。
3. PII read 同時要求 exact organization scope、允許的角色、明確用途與單一 application target；其他 organization 一律不可見。
4. CRM list／batch response 不回傳可直接聯絡或核身的完整 PII。完整值只由獨立 detail/reveal boundary 提供。
5. Audit 記錄存取事件與資料類別，不記錄 plaintext、ciphertext、token、raw entry reference 或完整 request／response body。
6. Production 不接受 plaintext master key runtime environment variable；root key 由 Google Cloud KMS 管理。
7. 刪除期限屬於資料模型與worker contract，不得只依人工維運或文件約定。

## 蒐集決策

| 欄位 | 是否蒐集 | 儲存 | 預設揭露 |
| --- | --- | --- | --- |
| applicant name | 志工申請必要 | application-level authenticated encryption | CRM list masked／最小識別；同 organization 指定 reviewer 在 detail 可看完整值 |
| phone | 志工聯繫必要 | application-level authenticated encryption | CRM list 顯示 masked phone；同 organization 指定 reviewer 在 detail 可看完整值 |
| basic profile | 只收審核必要欄位 | encrypted structured payload；欄位 allowlist + schema version | 依欄位與角色最小揭露 |
| national ID／insurance identity | 一般申請不收；只有 `insurance_required=true` 且保險流程明確需要時收 | 短期 authenticated encryption | 一般 reviewer／admin 不可見；指定 insurance role 只在單一案件、明確用途下使用 |

### 身分證字號特殊規則

1. 首選由保險方或專用核驗流程直接收集；StrayHub 只保存 `insurance_verified`、`insurer_reference`、`verified_at` 與使用的 policy version。
2. StrayHub 不得因收容所勾選 `insurance_required` 就自動長期保存身分證字號；仍需獨立用途說明與同意。
3. 若必須暫存，核驗完成後立即排入刪除，絕對上限為 30 天；withdraw／reject 且不再需要核驗時提前刪除。StrayHub 的 legal hold 不得延長此期限；若書面義務要求保留更久，必須由保險方或另一個經法遵核准的專用system of record直接承擔，StrayHub只保存核驗結果與外部reference。
4. API 不回傳完整值。UI 最多顯示 masked confirmation 或 `已完成核驗`。
5. 身分證字號不得建立一般搜尋索引、匯出欄位或通知 payload。

## Application profile模型邊界

PII 不直接加入 `users.display_name` 或一般 `VolunteerApplication` list projection。使用一筆與 application 一對一、帶 `organization_id` 的 encrypted profile，至少保存：

```text
application_id
organization_id
applicant_name_ciphertext
phone_ciphertext
basic_profile_ciphertext (nullable)
insurance_identity_ciphertext (nullable, short-lived)
encryption_algorithm
encryption_key_version
retention_expires_at
insurance_identity_delete_after (nullable)
pii_deleted_at (nullable)
created_at / updated_at
```

- 每一個 ciphertext 使用 field-specific associated data，至少綁定 `organization_id`、`application_id`、field name 與 schema version，避免跨欄位／跨tenant搬移。
- Ciphertext 使用 random nonce 的 authenticated encryption；不得用可比較 ciphertext 作搜尋。
- 若未來需要姓名／手機精確搜尋，另用獨立 search key 建立 normalized HMAC blind index；不得重用 encryption key，也不得支援模糊查詢直到有明確需求與風險評估。
- `encryption_key_version` 是每筆資料的必要欄位；unknown／disabled version 必須 fail closed。
- `pii_deleted_at` 後所有 reveal operation 必須回傳已刪除狀態，不得以 backup 或 audit 還原到一般CRM。

## CRM可見性與角色

| Actor | Name | Phone | Insurance identity |
| --- | --- | --- | --- |
| applicant本人 | 可查看自己的申請姓名 | 自己的手機；一般畫面可masked | 不回傳完整值，只顯示核驗狀態 |
| same-org designated reviewer | detail完整 | list masked、detail完整 | 不可見 |
| same-org shelter admin | detail完整 | list masked、detail完整 | 預設不可見 |
| same-org general staff | masked／案件必要識別 | masked | 不可見 |
| same-org insurance role | 必要時完整 | 必要時完整 | 單一案件、明確保險用途、限時揭露 |
| other organization | 不可見 | 不可見 | 不可見 |
| platform support/admin | 預設masked；不因平台角色自動解密 | 預設masked | 不可見 |
| break-glass support | 單一案件、理由、限時、完整audit | 單一案件、理由、限時、完整audit | 預設不允許；需額外核准流程 |
| notification worker | 只取得完成通知所需資料 | 受控一次性使用，不記錄 | 不可見 |

`SHELTER_ADMIN` 不是跨organization PII權限。Platform support 必須使用既有 target organization + support reason lifecycle；一般 platform scope 不得直接查詢 encrypted profile。

## CRM response分層

1. **List／batch**：application id、狀態、時間、masked display fields；不得包含 ciphertext、完整手機、身分證或LINE user id。
2. **Detail**：同 organization 授權角色可取得工作必要欄位；每次完整PII reveal必須audit。
3. **Insurance reveal／verify**：獨立permission與purpose boundary；不得混入一般application detail response。
4. **Export**：P0不提供。未來若新增，需另行風險評估、短效artifact、下載audit與到期刪除。

## 保存與刪除

| 生命週期 | 姓名／手機／basic profile | Insurance identity |
| --- | --- | --- |
| pending | 保留至決定；無活動最長 180 天 | 僅核驗需要時暫存 |
| rejected／withdrawn | terminal time + 180 天後刪除或匿名化 | 不再需要時立即刪除；最長 30 天 |
| approved + active/upcoming grant | 保留於工作必要期間 | 核驗後立即刪除 raw value |
| expired／revoked grant | 最後 effective grant 結束 + 180 天後刪除或匿名化 | 不保留 raw value |
| documented legal hold | 僅保留核准範圍，到期需重新核准 | 不得保留raw value超過30天；較長義務移交保險方或法遵核准的專用system of record |

- Application／Grant／Batch／Audit 的授權責任歷史可以保留，但必須與可識別PII分離；刪除profile後以 internal UUID、狀態、policy snapshot與時間維持稽核鏈。
- Retention worker只處理到期profile／insurance field，使用 organization scope、bounded batch、idempotent write與audit event。
- 刪除必須涵蓋主要DB、search index、notification payload與短效export。Backup依平台backup lifecycle自然到期，不能作一般使用者查詢來源。
- 法遵hold需要 `reason_code`、核准actor、`hold_until`與來源依據；到期後自動回到刪除queue。它可以延長姓名／手機／basic profile的期限，但不能延長StrayHub raw insurance identity的30天硬上限。

## PII access audit

每次 reveal、update、delete、insurance verify、export attempt與break-glass至少記錄：

```text
operation_id
occurred_at
actor_user_id or allowlisted system actor
actor_role
organization_id
application_id
action
data_category
purpose_code
result
request_id
policy_version
encryption_key_version
```

允許的action至少包括：

```text
pii.revealed
pii.updated
pii.deleted
pii.export_attempted
insurance_identity.submitted
insurance_identity.verified
insurance_identity.deleted
pii.break_glass_accessed
pii.retention_hold_changed
```

Audit的 `before_data`／`after_data` 只能保存 allowlisted metadata，例如欄位是否存在、masked狀態、key version、retention deadline與result；不得保存plaintext、ciphertext、blind index或provider body。

PII reveal必須與audit fail-closed耦合：在任何plaintext離開server boundary前，先以同一request的受控transaction成功持久化對應audit record；audit flush／commit失敗時拒絕揭露並回固定安全錯誤。不得先回傳plaintext再非同步補audit，也不得因audit service不可用而降級成未稽核揭露。

## Production encryption key與runtime

### Production

- Root／key-encryption key使用 Google Cloud KMS，例如 `strayhub-pii-kek`。
- Cloud Run application service account只有指定 CryptoKey 的 encrypt/decrypt使用權；KMS admin、rotation與IAM管理由不同管理權限負責。
- 使用 envelope encryption：data encryption key加密PII，KMS只wrap／unwrap data key。DB保存ciphertext、wrapped key metadata與key version。
- Secret Manager可保存KMS resource reference、encrypted keyset或其他runtime config，但不得保存可直接解密全部PII的plaintext master key。
- App啟動時production provider未設定、KMS不可用或key version未知時 fail closed；不得退回local key或plaintext。

### Local／test

- Local/test可使用獨立、非production AES-256-GCM key；只能處理虛構資料。
- Test key由測試fixture或未提交的runtime env提供，不進Git、不與production共用。
- 測試必須使用明顯虛構姓名、電話與身分識別值，且failure output不得印出sentinel plaintext。

## Key rotation與versioning

1. 每筆ciphertext保存algorithm與key version；associated data也包含schema version。
2. 正常情況每 180 天建立新KMS key version；疑似外洩、IAM誤配或未授權decrypt事件立即rotation。
3. 新version啟用後，新write只使用新version；舊version維持decrypt-only，直到資料完成rewrap／reencrypt。
4. Background rotation以bounded batch處理，對每筆資料先驗證tenant/application binding，再原子更新ciphertext與version並寫audit。
5. 所有資料完成遷移並完成read-back驗證後，才可停用舊version；不得先銷毀舊key。
6. Rotation失敗保留舊ciphertext，不得部分覆寫；unknown version與authentication-tag failure皆回固定安全錯誤。

## Task 5最低驗收條件

- [x] Model + reversible Alembic migration建立一對一、tenant-scoped encrypted profile，沒有plaintext PII column。
- [x] Encryption port與local/test AES-GCM adapter使用field-specific associated data並回傳key version。
- [x] Production provider設定fail closed；不接受production plaintext master-key fallback。
- [x] Service建立／讀取profile時驗證organization/application binding。
- [x] Ciphertext round-trip、wrong tenant/application/field AAD、tamper與unknown key version測試。
- [x] ORM／DB read-back證明plaintext不在PII columns，migration upgrade/downgrade/re-upgrade通過。
- [x] API response、Audit、exception與log redaction測試包含sentinel姓名、手機與身分識別值。
- [x] PII reveal在audit持久化成功前不產生plaintext response；audit flush／commit失敗時固定拒絕，且測試證明沒有未稽核揭露。
- [x] Insurance identity conditional collection與30天上限；一般申請不建立該ciphertext。
- [x] Retention deadline與soft-deleted profile fail-closed；實際worker／hard-delete可在後續獨立task交付，但不得遺失deadline。
- [x] Real PostgreSQL RLS證明same-org允許、cross-org與public scope拒絕。
- [x] Focused/full tests、Ruff、migration、staged snapshot與獨立security review通過。

Task 5 verification evidence（2026-08-23）：真實PostgreSQL runtime-role測試涵蓋public
create／reveal、persisted policy／membership locks、ORM ciphertext read-back與durable audit RLS；
empty-database測試執行0033 upgrade→0032 downgrade→0033 upgrade。最終candidate需維持full
pytest、Ruff、`git diff --check`及fresh independent P0/P1 review全數通過後才可commit。
