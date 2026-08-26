# 志工LIFF報名與LINE Bot散步回報流程

> 目的：確認志工從StrayHub Hub官方帳號完成LIFF報名、經合作收容所CRM核准後，能否在Hub LINE Bot中選擇「散步」並安全提交照護回報。
>
> 核心原則：LIFF負責身份綁定與志工申請；CRM負責資格審核；LINE Bot負責回報操作；Backend每次Webhook／postback都重新驗證有效Membership、Grant、Shelter Context與動物scope。

## 1. End-to-end flow

```mermaid
flowchart TD
    A[StrayHub Hub官方帳號] --> B{Rich Menu}

    B -->|志工報名| C[開啟StrayHub LIFF]
    B -->|照護回報| R0[LINE Bot收到postback]

    C --> C1[LIFF init／LINE login]
    C1 --> C2[Backend驗證LINE ID Token]
    C2 --> C3[選擇合作收容所：地區／公開清單]
    C3 --> C4[建立或重用LINE User Binding與organization context]

    C4 --> F[填寫志工基本資料]
    F --> F1[姓名／手機／其他基本資料]
    F1 --> F2{收容所是否需要保險?}
    F2 -->|否| F4[個資與志工申請同意]
    F2 -->|是| F3[填寫身分證字號與保險用途同意]
    F3 --> F4
    F4 --> G[送出Volunteer Application]
    G --> P[PENDING]
    P --> P1[只能查看自己的申請狀態]
    P1 --> P2[不可查看動物或提交照護回報]

    P --> H[被選收容所管理員登入CRM]
    H --> H1[只查看本organization的申請]
    H1 --> H2{審核結果}
    H2 -->|拒絕| X1[REJECTED／不可回報]
    H2 -->|核准| I[建立OrganizationMembership]
    I --> I1[建立VolunteerAccessGrant]
    I1 --> I2[ACTIVE]
    I2 --> J[志工再次開啟LIFF或使用Hub LINE Bot]

    R0 --> R1[驗證LINE Webhook signature]
    R1 --> R2[取得Webhook source.line_user_id]
    R2 --> R3{LINE Binding存在且active?}
    R3 -->|否| RX1[拒絕：先完成LINE／LIFF綁定]
    R3 -->|是| R4[解析User與目前LINE context]

    R4 --> R5{有效Membership與Grant?}
    R5 -->|否：PENDING／過期／撤銷| RX2[拒絕：尚未取得有效志工授權]
    R5 -->|是| R6{只有一個有效Shelter Context?}
    R6 -->|否：多個收容所或context不明| RX3[要求在LIFF選擇目前服務收容所]
    R6 -->|是| R7[建立或取得WebhookSession]

    R7 --> R8{Bot action}
    R8 -->|開始照護回報| R9[列出可回報動物]
    R8 -->|選擇散步| R10[進入散步回報問題]

    R9 --> R11[志工選擇動物]
    R11 --> R12{動物active且在reportable scope?}
    R12 -->|否| RX4[拒絕：動物不存在或無法回報]
    R12 -->|是| R13[確認動物]
    R13 --> R10

    R10 --> R14[建立或恢復Care Report Draft]
    R14 --> R15[回答散步完成／反應／備註等問題]
    R15 --> R16{提交前重新驗證授權與draft owner}
    R16 -->|失敗| RX5[拒絕：context／draft已失效]
    R16 -->|通過| R17[保存原始照護回報]
    R17 --> R18[背景派送AI分析或通知]
    R18 --> R19[LINE Bot回覆已保存]

    I2 -. 同一LINE identity .-> R0

    classDef entry fill:#eef2f7,stroke:#64748b,color:#172033;
    classDef liff fill:#eff8f5,stroke:#54a88d,color:#145c4b;
    classDef crm fill:#fff8ed,stroke:#d6853d,color:#7c4a13;
    classDef bot fill:#eaf2ff,stroke:#5b85c5,color:#1e477a;
    classDef deny fill:#fff1f2,stroke:#e11d48,color:#9f1239;
    classDef success fill:#e5f4ef,stroke:#2d8b73,color:#145c4b;

    class A,B entry;
    class C,C1,C2,C3,C4,F,F1,F2,F3,F4,G liff;
    class H,H1,H2,I,I1 crm;
    class R0,R1,R2,R3,R4,R5,R6,R7,R8,R9,R10,R11,R12,R13,R14,R15,R16,R17,R18,R19 bot;
    class P,P1,P2,X1,RX1,RX2,RX3,RX4,RX5 deny;
    class I2,J success;
```

## 2. 授權判斷

Bot每次收到postback或訊息，都要重新套用：

```mermaid
flowchart LR
    A[LINE user ID] --> B[Active LineUserBinding]
    B --> C[Active User]
    C --> D[Active Organization]
    D --> E[OrganizationMembership]
    E --> F[VolunteerAccessGrant]
    F --> G[WebhookSession／Shelter Context]
    G --> H[Reportable Animal Scope]
    H --> I[可提交散步回報]

    B -. 缺少 .-> X[拒絕]
    E -. 非VOLUNTEER／inactive .-> X
    F -. 未開始／過期／撤銷 .-> X
    G -. 多收容所或context不明 .-> X
    H -. 動物不可回報 .-> X
```

有效志工授權條件：

```text
organization.status == active
user.status == active
membership.role == VOLUNTEER
membership.status == active
membership.valid_from <= database_now < membership.expires_at
grant.status == active
grant.valid_from <= database_now < grant.expires_at
grant.organization_id == membership.organization_id
grant.user_id == membership.user_id
grant.membership_id == membership.id
```

## 3. 狀態結果

| 條件 | LINE Bot結果 |
|---|---|
| 尚未完成LIFF綁定 | 要求先完成LINE／LIFF綁定 |
| 已報名但PENDING | 拒絕照護回報，只顯示審核狀態 |
| CRM拒絕 | 拒絕照護回報 |
| CRM核准且Grant ACTIVE | 可開始散步回報 |
| Grant尚未開始 | 拒絕 |
| Grant已過期 | 拒絕 |
| Grant已撤銷 | 拒絕 |
| 收容所停用 | 拒絕 |
| 同一志工有多個有效收容所 | 要求在LIFF選擇Shelter Context |
| 動物不在reportable scope | 拒絕 |
| draft不屬於該志工或該organization | 拒絕 |

## 4. 邊界與資料流

```text
LIFF：
  LINE identity綁定、選擇合作收容所、shelter context、志工申請、基本資料、條件式保險資料

CRM：
  收容所管理員審核、建立Membership與Grant、撤銷／到期管理

LINE Bot：
  顯示照護選單、選擇動物、選擇散步、逐題回報、通知結果

Backend：
  Webhook signature、LINE binding、tenant scope、Membership、Grant、
  WebhookSession、reportable scope、draft owner、提交時重新驗證

Database：
  以organization_id與user_id雙重隔離；不信任postback內的organization或role
```

## 5. 需要團隊確認的產品決策

1. Hub官方帳號Rich Menu是否顯示`志工報名`、`照護回報`、`領養媒合`三個入口？
2. 一位志工同時支援多個收容所時，是否要求先在LIFF選擇目前服務單位？
3. 散步回報是否需要照片、備註、異常狀況與通知管理員？
4. Grant被撤銷或到期時，是否要主動透過Hub LINE Bot通知志工？
