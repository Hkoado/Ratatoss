# Coding agent handoff — RATATOSS UI

## 1. Absolute instructions

Read in the following order:
1. `docs/SOURCE_RATATOSS_BRIEF_v1.2.md` — **IMMUTABLE**, primary source.
2. `docs/UI_SPEC.md` + `docs/SCREEN_BLUEPRINTS.md` — frontend UX, states, feature gates.
3. `docs/DESIGN_TOKENS.md` + `docs/COMPONENT_DIMENSIONS.md` + `tokens.css` — **canonical** colors, spacing, responsive measurements.
4. `docs/FRONTEND_CONTRACTS.ts` — **proposal**, not established API schema.
5. `index.html`, `styles.css`, `app.js` — UI behavior/visual reference only.
6. Existing backend `API Contracts`, security requirements, database schema and implementation (if present) — compare before any integration.

Never edit the source brief, existing project vision documents, security requirements, or architecture baseline without explicit approval. Do not hallucinate versions, endpoints, login capabilities, Croc APIs, cryptographic guarantees, actual transfer metrics, network classes or test successes. **If something cannot be verified, mark it UNKNOWN and surface an issue.**

## 2. PLAN prompt for Astra (copy into planning agent)

> Bạn là Senior Frontend Architect phụ trách Ratatoss. Đọc kỹ `docs/SOURCE_RATATOSS_BRIEF_v1.2.md`, `docs/UI_SPEC.md`, `docs/SCREEN_BLUEPRINTS.md`, `docs/DESIGN_TOKENS.md`, `docs/COMPONENT_DIMENSIONS.md`, `docs/FRONTEND_CONTRACTS.ts`, sau đó khảo sát cấu trúc repo và API contracts thật (nếu tồn tại). Lập kế hoạch triển khai UI gồm architecture, routes, components, design tokens, state boundaries, service adapters, authentication decision points, error states, accessible graph, responsive behavior, test plan, feature flags và danh sách blocking questions. Ưu tiên MVP batch pipeline/verified delivery; PLARS adaptive và SafeExit vẫn khóa theo giai đoạn. **Không sửa tài liệu gốc, không phát minh API, không giả định Croc có streaming piece API.** Phân biệt MUST/SHOULD/LATER, chú rõ tài liệu/đường dẫn làm căn cứ. Đầu ra: plan + actionable checklist; chưa viết code.

## 3. ACT prompt for Sol (copy into coding agent)

> Thực thi đúng kế hoạch Astra đã duyệt cho UI Ratatoss. Bám `docs/UI_SPEC.md`, `docs/SCREEN_BLUEPRINTS.md`, `docs/DESIGN_TOKENS.md`, `docs/COMPONENT_DIMENSIONS.md`, ưu tiên UI hiện hữu và `tokens.css`, không redesign vô cớ. Dùng prototype HTML/CSS/JS làm visual/interaction reference, không coi mock data là backend thực. Các màn phải có: login placeholder, dashboard, peer picker, send flow, node/edge transfer visualization, history, settings, light/dark. Tách UI view models / API adapters; mapping chỉ trên endpoints và payload đã kiểm chứng trong repo. Nếu thiếu API hoặc auth, giữ mock mode hiển thị rõ `DEMO` và tạo typed interface + TODO, tuyệt đối không tạo endpoint bí mật. Trạng thái file `verified` phải khác tiến độ byte; chỉ VERIFIED/AVAILABLE batch mới là nguồn forward; SafeExit và spare replication mặc định OFF và feature-gated. Lập tests cho UI interactions, empty/error/loading/offline/reconnect, keyboard, responsive và reduced-motion. Sau mỗi phần, cung cấp changed files, test commands/results, diff summary và unresolved questions. **Không sửa source brief hoặc kiến trúc gốc.**

## 4. Recommended frontend architecture (PROPOSAL, not baseline requirement)

If the project's selected frontend already uses Next.js, prefer its current stable installed version and existing conventions. If not, choose a validated React + TypeScript framework in an **architecture decision record**. **Do not install or upgrade packages solely because this doc lists a possibility.**

```text
src/
  app/                         # routes / layouts (framework-specific)
  components/
    shell/                      # Sidebar, Topbar, ThemeControl
    devices/                    # PeerCard, PeerPicker
    transfers/                  # TransferGraph, NodeCard, Edge, Inspector,
                                # RecipientProgress, EventStream
    forms/                      # FilePicker, JobConfig
    feedback/                   # Empty, Error, Skeleton, StaleBanner
  features/
    auth/                       # real auth only once approved
    peers/                      # api + view model mapper + feature logic
    jobs/                       # api + view model mapper + feature logic
    preferences/
  lib/
    api/                        # approved API client, no silent fallback
    query/                      # loading/retry/reconciliation
    types/                      # API vs view types separated
  styles/                       # migrate exact values from tokens.css + styles.css
  tests/
```

Potential `reactflow/@xyflow` usage for production graph is a **design option**, not a requirement. For a 4-node MVP, accessible SVG with tested keyboard behavior is enough. Any package choice must match the repo, license and performance.

## 5. Implementation tasks and definition of done

- [ ] Capture baseline screenshot of prototype at desktop + mobile in dark/light.
- [ ] Verify `tokens.css` is loaded before `styles.css`; run token-missing check, update `design-tokens.json` if CSS tokens change.
- [ ] Keep exact component sizes/breakpoints from `COMPONENT_DIMENSIONS.md` until change approved.
- [ ] Move shell/layout into framework (if required), keep sidebar dimensions and orange theme.
- [ ] Build UI state machines; `UNKNOWN`/`STALE` rendering and retry state.
- [ ] Wire approved human auth or retain clearly marked placeholder (do not invent credentials).
- [ ] Integrate authorized peer list; filter/choose; never infer LAN from local IP.
- [ ] Connect file selection to a **reviewed** source-file handoff approach and real `/jobs` contract.
- [ ] Implement real job status mapping from `GET /jobs/{id}/status` if response contract exists.
- [ ] Render node/edge graph from assignments/measurements; show unknown when not measured.
- [ ] Implement truthful completion/verification, offline/recovery and idempotent update handling.
- [ ] Implement settings only where Agent/Controller can apply them; otherwise label local-only.
- [ ] Feature gate PLARS adaptive and SafeExit; no optimistic `safe to exit`.
- [ ] Run accessibility, responsive, regression and security checks.
- [ ] Produce handoff notes + exact test results; unresolved backend questions remain visible.

## 6. Prototype constraints

Current UI contains a **RAM-only** session simulator with 4 example peers; a timer increments fake recipient percentages; a fake C offline toggle; local-only filename/size selection; theme preference in `localStorage`; demo profile name/email with **no authentication**. These are *intentional* UX fixtures and must not be copied into production data services. The demo does **not** hash, split, read bytes, invoke Croc, discover real LAN, store files, make API calls, transfer or verify anything.

## 7. Stop conditions

Stop implementation and ask for architectural clarification **only for the blocked component** when encountering an unavailable contract, missing auth design, insecure requirement, or incompatible backend. You may continue independent UI layout work. Never silently mock a production success condition.


## v1.2 — Brand/UI override (áp dụng trước khi coding)

1. **Logo bắt buộc:** ưu tiên ảnh sóc gốc trong `assets/ratatoss-logo-original.png`, sử dụng ảnh `ratatoss-logo.webp` để render và `ratatoss-favicon.png` cho tab. Không tạo lại ký hiệu R. Giữ tỷ lệ và nền trong suốt.
2. **Cấm glow và shadow trang trí** kể cả trên logo, node, card, dialog, hover. `box-shadow:none`, `filter:none`, `backdrop-filter:none`; focus-visible có outline rõ ràng.
3. **Icon bắt buộc rõ:** một hệ outline 24×24, stroke 1.85px, round cap/join; dùng SVG gốc trong `app.js` hoặc thay đồng nhất cả bộ bằng một thư viện như Lucide (được phê duyệt sau khi kiểm tra dependency). Không vẽ gear bằng polygon méo hoặc đường luồng chồng lên nhau.
4. **Compact copy:** tiêu đề chức năng ngắn, chỉ một DEMO badge trong topbar, bỏ thẻ mô tả KPI và phần nguyên tắc trùng lặp ở dashboard. Tuyệt đối không ẩn lỗi, bảo mật, trạng thái xác minh.
5. **Source of truth token:** `tokens.css` → `design-tokens.json` qua `python scripts/build_preview.py`. Kích thước hiện hành ở cuối `docs/COMPONENT_DIMENSIONS.md`. Không sửa `SOURCE_RATATOSS_BRIEF_v1.2.md`.
6. **Acceptance:** so ảnh dark/light và mobile, kiểm tra logo đã load, SVG không méo, không có CSS shadow/glow thực tế, chuyển trang được, đồng hồ giả lập không đồng nghĩa truyền Croc.
