# Ratatoss — Screen Blueprints, Interaction States & UI Contracts

**Document ID:** `RAT-UI-FLOWS-001` · **Version:** 1.1.0 · **Audience:** frontend coding agent / UI reviewer · **Status:** proposal grounded in Ratatoss Product Brief v1.2.

> This document defines the **interface**, not a claim that backend capabilities exist. Source priority: `SOURCE_RATATOSS_BRIEF_v1.2.md` > approved backend API contract > `UI_SPEC.md` > this blueprint > demo source code. When a backend detail is unspecified, represent it with `UNKNOWN` and stop integration for that interface. Do not modify the source brief.

## 1. Information architecture

```text
App Shell
├── Login / local demo profile      (overlay or /login)
├── Tổng quan                       /dashboard
├── Thiết bị                        /peers
│   └── Peer details / selection    inline panel or dialog
├── Gửi tệp                         /send
│   ├── 1. File source
│   ├── 2. Authorized recipients
│   └── 3. Strategy + summary
├── Luồng truyền                    /transfers/:jobId
│   ├── Node-edge topology
│   ├── Verified recipient progress
│   ├── Selected node inspector
│   ├── Activity / recovery panel
│   └── Job status
├── Lịch sử                         /history
│   └── Job detail → /transfers/:jobId (only for existing job)
└── Cài đặt                         /settings
    ├── Appearance
    ├── Resource budgets (local form until API approved)
    ├── SafeExit / replication (disabled MVP)
    └── Connection/security explanation
```

**Navigation labels** are user-facing Vietnamese. Technical terms such as `peer`, `batch`, `pipeline`, `RX/TX` may remain in English but must be explained in tooltip/subtitle on their first occurrence. Sidebar item order must remain stable. Do not add an admin/benchmark module without a separate design requirement.

## 2. Global screen anatomy and UI assets

```text
┌─────────────────244px────────────────┬────────────────────────────────────────────┐
│  Logo + Ratatoss brand               │ Topbar (64px desktop / 65px tablet)        │
│  Navigation                          ├────────────────────────────────────────────┤
│  • Tổng quan                         │ Page heading / subtitle / quick actions    │
│  • Thiết bị                          │ Persistent DEMO badge if simulation        │
│  • Gửi tệp                           │                                            │
│  • Luồng truyền                      │ Page body: 12-ish column responsive cards   │
│  • Lịch sử                           │                                            │
│  • Cài đặt                           │                                            │
│  Prototype indicator                │                                            │
│  Demo profile                       │                                            │
└──────────────────────────────────────┴────────────────────────────────────────────┘
```

**Global visual rules:** source orange `#F47A28`, use semantic themes; all card widths fluid; primary actions only one or two per screen; error messages next to the failed action; status words adjacent to icons, never color alone. Complete component sizes live in `COMPONENT_DIMENSIONS.md`, tokens in `DESIGN_TOKENS.md`.

## 3. Each page: fields, controls, states and behavior

### UI-01 · Login / Account

**Goal:** view a sample local identity screen without implying human auth exists in the original brief.

- Inputs in demo: display name (required, max 36 chars), optional/display-only sample email; **never prompt a real password**. Login button must explicitly say `demo`.
- Real production: a human login flow is **not specified in the source brief**. Only integrate after auth choice, cookie/session plan, CSRF protections, roles/device pairing, session expiry and API contracts are explicitly agreed.
- States: `not-signed-in`, `editing`, `invalid-input`, `signed-in-demo`, `submitting` (production only), `auth-expired` (production only), `network-error` (production only).
- Interaction: profile/avatar opens dialog; Esc and Close closes; focus is trapped and restored; logout resets local demo profile (not job/batch data). Changing visible name does not authorize peer access.
- Acceptance: cannot display `Đã xác thực` based on demo form submission; local profile data is not an Agent credential or Croc secret.

### UI-02 · Dashboard / Tổng quan

**Goal:** get instant status and enter active job without misreporting actual transfer results.

**Sections and ordering:** Page header → 4 summary tiles → graph preview + recipient progress → recent events + 4 explanatory principles.

| Tile | Data field | Empty / unknown | Rule |
|---|---|---|---|
| Active jobs | backend running job count | `0` if confirmed, `—` if not fetched | `0` ≠ `UNKNOWN` |
| Network peers | authorized known peer count | `—` or `Chưa có máy` | Presence separately tracked |
| Avg bytes received | `sum(recipient.receivedBytes)/sum(recipient.totalBytes)` | `—` if no valid denominators | **Not** fileVerified/makespan |
| Verified recipients | count where `fileVerified === true` / total | `0/0` only if known | 100% received may still be VERIFYING |

**Actions:** `Xem thiết bị` goes UI-03; `Gửi tệp mới` UI-04; graph card link UI-05. **Not present yet** in demo: real goodput, ETA, WAN byte telemetry. Show unknown rather than deriving from fake speeds.

**States:** `no-jobs`, `running`, `verifying`, `all-verified`, `partially-failed`, `telemetry-stale`, `loading`, `network-error`.

### UI-03 · Devices / Thiết bị

**Goal:** select authorized, eligible, reachable recipients; never select source A.

**Card anatomy:** icon 43×43 → device displayName → site/alias → measured connection label → source/recipient role → presence + capability → select/deselect.

**Fields:** `peerId`, `displayName`, `presence`, `lastHeartbeatAt`, `isSource`, `canReceiveJob`, `canForward`, `linkClass`, `linkMeasuredAt`, `maxRxSessions`, `maxTxSessions` and optional telemetry (`rxGoodputBps`, `txGoodputBps`). Fields not supported should be hidden or `Chưa đo`.

**Rules:**
- `ONLINE` means valid fresh heartbeat according to backend policy; `STALE` ≠ online.
- If `canReceiveJob=false`, control disabled and reason explicit. Source is not a recipient.
- `LAN_VERIFIED` only from actual path check; same Wi-Fi / subnet / private IP insufficient (source §3/F3).
- Multiple peers can be selected. Selections are preserved when navigating to Send, but stale eligibility must be revalidated at submission.
- Search filters locally across current authorized list; empty list and no-search-matches are distinct UI states.

**Interactions:** peer select via button with `aria-pressed`; search input; continue to send; optional more-info inspector only once backend fields approved. No device discovery from ordinary browser APIs in demo.

### UI-04 · Send / Gửi tệp

**Goal:** three-step, minimal-click file distribution configuration.

1. **File:** user picks exactly one file in MVP. Display name, byte size and remove option. Drag/drop and keyboard accessible. Browsers supply metadata, but **source file must become readable by local Agent via an explicitly approved handoff protocol**. Do not treat an HTML File object as a remote Controller filesystem path.
2. **Recipients:** choose one or more eligible peers. `A` excluded. Show count in summary. Revalidate permissions and reachability at job creation.
3. **Mode / review:** `FIXED_PIPELINE` concept is MVP; `DIRECT` and `GATEWAY` are research baselines only when implemented; `ADAPTIVE_PLARS` disabled until phase 2. SafeExit and spare-copy replication OFF by default. Display source size, recipients, strategy, verification policy, warning and submit.

**Button enabled iff** file metadata is valid, `eligibleRecipientIds.length > 0`, not submitting and all required authorization/Agent checks pass (for demo, just valid metadata and recipient selection; label `Khởi chạy mô phỏng`).

**States:** `idle` (empty), `file-selected`, `recipient-selected`, `invalid-file`, `invalid-target`, `submitting`, `accepted`, `rejected`, `source-agent-unavailable`, `permission-denied`, `controller-offline`.

**Backend boundary:** Brief §6 lists `POST /jobs` but does **not** specify payload/file staging semantics. Agent must not invent multipart upload/absolute path behavior, auth headers, idempotency keys or endpoint responses. When approval is absent, preserve demo and document integration blocker. Success navigates only after receiving a real `job_id` and confirmed acceptance.

### UI-05 · Transfer / Luồng truyền

**Goal:** make simultaneous receive/forward visible without conflating transfer with verification.

**Required panels:** Job header (name, size, job ID, status) → 3 job KPI tiles → node/edge graph → recipient verification rows → selected node inspector → event log + error/recovery panel.

**Graph node anatomy:** peer icon, display name, location/role, byte received %, verification state, online/offline/stale indicator, keyboard focus/selection. UI only draws **authorized recipients** from this job, plus source; not unrelated nearby peers. For demo it uses A/B/C/D scenario, no real assignment feed.

**Edges:** `fromPeerId`, `toPeerId`, `linkClass`, actual `activeAssignmentIds`, `state`, measured goodput or `Chưa đo`, optional common bottleneck. Orange = active transfer, blue = measured LAN, neutral dashed = candidate/unknown, red = offline/failed. In production an edge must **not** animate as active if it has no current backend assignment or telemetry is stale. Direct A→D is conditional, never universally forced.

**Peer detail inspector:** selected ID/name/role, presence, received/verified bytes, available batches, active RX/TX sessions, assigned tasks, errors, last update. If actual batch data absent, show `Chưa có dữ liệu`, not a fabricated number.

**Recipient state machine** (source §6): `MISSING → ASSIGNED → TRANSFERRING → RECEIVED → VERIFIED → AVAILABLE`; error `TRANSFERRING → RETRY_PENDING`, corruption `RECEIVED → CORRUPT → RETRY_PENDING`.

**File verified rule:** `receivedBytes===totalBytes` is only receipt; all piece hashes + full-file SHA-256 must match before the recipient is `COMPLETED_VERIFIED`. Only verified/durable batches can be forwarded. Confirmed completed job = **every** designated recipient full-file verified; this defines makespan (source §1/§4).

**Offline/reconnect:** when C drops, preserve verified bytes/state at all peers, mark in-flight assignments unknown/failed until authoritative recovery. Once C returns, reconcile on-disk manifest, don't reset progress to 0. Spinner/animation must not imply real recovery while Controller is disconnected.

**UI-specific states:** `QUEUED`, `RUNNING`, `PAUSED` (only if backend supports it; demo pause only), `VERIFYING`, `PARTIAL`, `COMPLETED_VERIFIED`, `FAILED`, `UNKNOWN`, `STALE`. Distinguish `PAUSED` from no telemetry. Optional controller shutdown → stale, not completed.

**Long peer lists:** virtualized list, group by LAN/site and scroll/zoom graph. Never shrink labels below usability to fit 20 nodes on a static 376px canvas.

### UI-06 · History / Lịch sử

**Goal:** evidence-based job audit, not fake benchmark results.

- Each row: file name/size, count of intended recipients, `job_id`, start/end time, count full-file verified, failure/partial state, link to details.
- Filters/search only if API supports pagination & history; exact endpoint is **not defined** in brief.
- Demo stores completed simulated jobs in page memory only; refreshing clears.
- Error/loading/empty states distinct. Do not claim `SHA-256 verified` from bytes delivered without ACK + full hash status.

### UI-07 · Settings / Cài đặt

**Sections:** Appearance (theme), UX (language), Resource budgets (RX/TX max sessions, bandwidth, queue) and Security/Connectivity notes.

- Appearance toggles real UI theme locally. Both theme palettes defined in `tokens.css`.
- Resource controls in demo are **not connected** to Agent, and must state this clearly. Production changes require supported controller/Agent configuration contract and feedback whether applied.
- SafeExit levels and opportunistic spare-copy replication are **disabled in MVP**, not merely switched off cosmetically. Future controls need explicit opt-in, consequences and validation before telling sender it can leave.
- E2E payload encryption across intermediate peers is an extension. Do not call Croc per-hop encryption end-to-end A→D.
- No screen should expose Croc session codes, device token, manifest private key, raw network secrets or agent credentials.

## 4. Cross-screen UX state matrix

| Condition | Dashboard | Devices | Send | Transfer | History | Settings |
|---|---|---|---|---|---|---|
| Initial loading | Skeleton KPI | Skeleton device grid | Disabled start | Graph loading placeholder | Table skeleton | Pref load |
| Empty | 0 confirmed jobs | Empty peer list | Blank picker | No selected job | Empty illustration | defaults |
| Error from API | Error + retry | Inline error + retry | Prevent submit | Keep last safe snapshot + error | Error + retry | revert/failed save |
| Telemetry stale | `Dữ liệu có thể cũ` | `STALE` peers | Revalidate before submit | Freeze active animations + last timestamp | Display last snapshot | Do not claim applied |
| Unauthorized | Auth required | No target data | Block send | Block protected job | Block private data | Auth/error |
| Network disconnected | Reconnect banner | Presence unknown | Disable real submit | No fake live flow | Show cache as stale | Local-only options work |
| Prefers reduced motion | No KPI animation | No animated hover needed | No transient spin | Static edge + legend | Static | Static |

## 5. Backend view model boundary and explicit gaps

Use `FRONTEND_CONTRACTS.ts` as **view model proposal** only, not a server schema. Brief §6 guarantees only *suggested routes*:

```text
POST /jobs                      (request & response shape TBD)
POST /peers/register            (Agent use)
POST /peers/heartbeat           (Agent use)
GET  /peers/{id}/assignments    (Agent use)
POST /assignments/{id}/ack      (verified/durable ACK)
POST /assignments/{id}/fail     (Agent failure reporting)
GET  /jobs/{id}/status          (shape TBD)
```

**Blocking integration decisions:** human authentication contract; browser ↔ local Agent file handoff; authorized peer list/discovery UI endpoint; immutable event revision/order; history endpoint and retention; pause/cancel control; WebSocket subscription for job telemetry; link measurement semantics; exact verified-file event. Each is **unresolved** until backend documents exist. Do not silently create `GET /ui/peers` or `WS /events` and call it official.

## 6. Agent implementation sequence and checks

1. Load `tokens.css` before `styles.css` and match dark/light screenshot at 1440×900 / 390×844.
2. Extract shell into components (Sidebar, Topbar, Card, Button, Badge, ThemeController). Keep token names stable.
3. Build UI-03 and UI-04 with state validation, then UI-05 graph+list. Keep mock adapter clearly separate from server adapter.
4. Render recipients and edges from real `JobView` only after exact contract confirmation. Test `received=100%, fileVerified=false` explicitly.
5. Add stale/network-error/permission-denied/partial-recovery states before connecting real jobs.
6. Review accessibility: focus trap for modal, keyboard navigation, hit areas, color contrast, no page overflow, reduced motion.
7. Add tests: A→B/C pipeline illustration; offline C after verified batches; C returns without reset; D direct conditional; no SafeExit toggle; no replication by default; repeated events idempotent; empty/error fallback.
8. Record screenshots and verification logs; do **not** mark backend integration complete just because demo timer animates.

## 7. Copy rules and microcopy glossary

| Meaning | Approved user-facing wording | Never say |
|---|---|---|
| Bytes received | `Đã nhận 68% dữ liệu` | `Đã hoàn tất 68% file` without qualification |
| All bytes but not verified | `Đã nhận đủ, đang xác minh SHA-256` | `Hoàn tất` |
| Verified batch | `Batch đã lưu và xác minh` | `Đã forward` before TX actually assigned |
| Verified file | `Tệp đã xác minh thành công` | `100%` as sole evidence |
| Unknown goodput | `Chưa đo` | `Đường truyền tốt` |
| LAN classification | `LAN đã kiểm chứng` | `Cùng Wi‑Fi = LAN` |
| Candidate route | `Đường có thể sử dụng` | `Đang truyền` |
| Demo/mock | `Mô phỏng — không truyền dữ liệu thực` | `Truyền thành công` |
| Source SafeExit not guaranteed | `Máy nguồn chưa đủ điều kiện rời mạng an toàn` | `Bạn có thể tắt máy` in normal mode |



## Blueprints rút gọn v1.2 (UI đang triển khai)

- **Tổng quan:** một dòng tiêu đề, CTA `Xem thiết bị` và `Gửi tệp mới`, bốn KPI 1 hàng (desktop), graph 4 node và tiến độ từng peer; loại bỏ phần diễn giải nguyên tắc bên dưới.
- **Thiết bị:** tiêu đề + danh sách card và tìm kiếm/đánh dấu; không banner kỹ thuật; trạng thái offline vẫn phải rõ và không cho chọn peer offline.
- **Gửi tệp:** chọn file, chọn peer, cấu hình/sơ lược, CTA khởi chạy mô phỏng. Không hiển thị giải thích dài lặp trên các bước. Không giả định browser có quyền truy cập đường dẫn file nguồn khi đóng gói desktop.
- **Luồng truyền:** KPI, graph, inspector, trạng thái xác minh, nút pause/resume và giả lập C offline/reconnect. Giữ status/metrics hữu ích, bỏ giải thích lặp.
- **Lịch sử:** danh sách phiên, empty state đơn giản, timestamp; chưa có DB thì không khẳng định persistence.
- **Cài đặt:** theme, cấu hình thử nghiệm, các feature gate bảo mật; SafeExit/spare replication vẫn off.
- **Login:** logo sóc nhất quán; đăng nhập demo chỉ nhận tên hiển thị, email trong RAM; không lấy mật khẩu.
- **Dark/light:** mọi màn dùng semantic vars; không bóng, không glow; responsive 320–1440px phải không tràn ngang.
