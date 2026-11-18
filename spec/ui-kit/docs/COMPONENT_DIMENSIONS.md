# Ratatoss — Component Dimensions & Responsive Layout

**Mã:** `RAT-UI-SIZES-001` · **Phiên bản:** 1.2.0 · **Đơn vị:** CSS px ở browser zoom 100%, không phải dp vật lý. **Nguồn code:** `../tokens.css`, `../styles.css`. Đây là thông số **UI đề xuất**, không có trong Product Brief v1.2.

## 1. Design canvas và breakpoints

| Viewport (CSS px) | Sidebar | Topbar | Content padding (top/right/bottom/left) | KPI columns | Đồ thị & peer progress | Device grid | Ghi chú |
|---|---:|---:|---|---|---|---|---|
| **>1300** | 244 cố định | 64 | 24 / 30 / 36 / 30 | 4 | `1.65fr / minmax(290px,.85fr)` | 3 | Bố cục desktop chính |
| **1101–1300** | 220 cố định | 64 | 29 / 27 / 50 / 27 | 4 | `1.4fr / minmax(260px,.8fr)` | 3 | Desktop hẹp |
| **851–1100** | 220 cố định | 64 | 29 / 27 / 50 / 27 | 2 | 1 cột (stack) | 2 | `lower-grid` vẫn 2 cột |
| **561–850** | 240 off-canvas | 65 | 22 / 20 / 40 / 20 | 2 | 1 cột | 2 | Menu hamburger; content toàn chiều rộng |
| **≤560** | 240 off-canvas | 65 | 18 / 14 / 40 / 14 | 2 | 1 cột | 1 | Topology height 320; node 117 |

**Điểm cắt CSS:** `@media (max-width: 1300px)`, `1100px`, `850px`, `560px`. Ở đúng điểm cắt phải áp dụng hàng phía dưới (ví dụ 850px dùng off-canvas). Breakpoint token `--rt-breakpoint-*` là tài liệu để đồng bộ, không thể thay trực tiếp điều kiện `@media` bằng `var()`.

**Kích thước thiết kế tham khảo khi review:** desktop 1440×900, laptop 1280×800, tablet 768×1024, mobile 390×844 và mobile nhỏ 320×700. Đây là viewport QA, không phải responsive breakpoint bổ sung.

## 2. App shell

| Component / CSS selector | Chiều rộng | Chiều cao | Padding / gap | Radius / border | Chính xác khi nào |
|---|---|---|---|---|---|
| `.app-shell` | viewport | ≥100vh | `display:flex` | — | Mọi viewport |
| `.sidebar` | 244 / 220 / 240 | 100vh | `22px 15px 17px` | border-right 1px | Desktop / compact / off-canvas |
| `.brand-logo` | 54 | 42 | object-fit contain | 0 / không shadow | Desktop; mobile 49×38 |
| `.brand` | theo sidebar | auto | gap 10; padding `0 8px 24px` | — | Mọi viewport |
| `.nav-btn` | 100% sidebar content | 42 | gap 12; padding `0 12px` | 9 | Mọi viewport |
| `.engine-card` | ẩn | ẩn | Loại bỏ khỏi UI | — | Chỉ giữ nhãn DEMO trên topbar |
| `.avatar` | 36 | 36 | — | 10 | Sidebar/topbar |
| `.topbar` | toàn main | 64px min / responsive legacy 65px | left/right theo breakpoint | border-bottom 1px | Desktop / tablet / mobile |
| `.icon-btn` | 37 | 37 | centered | 10 / stroke 1 | Mọi viewport |
| `.content` | max-width 1640 | auto | theo bảng breakpoint | — | Max width tính trên `.main` |
| `.page-head` | fluid | auto | gap 18; bottom margin 20 | — | Wrap ở ≤850 |
| `.page-head h1` | fluid | auto | font `clamp(24px, 2.25vw, 29px)` | — | Mobile 24px |
| `.eyebrow` | ẩn | — | Không render trong header mới | — | Toàn app |

**Lưu ý desktop:** `max-width:1640px` là độ rộng khung content; sidebar 244px nằm bên ngoài khung. Không đặt toàn viewport ở mức 1640px rồi trừ sidebar lần hai.

## 3. Design components (kích thước cấu thành)

| Component | Measurements theo prototype | Token / selector | Mô tả |
|---|---|---|---|
| Primary/secondary/ghost CTA | padding `11px 16px`; gap 9; radius 10; font 12/800 | `.btn`; `--rt-button-*` | Chiều cao thực phụ thuộc line-height; target 44px trong bản production |
| Small button | padding `8px 12px`; radius 9; font 11 | `.btn.small` | Không phải touch target 44px; cần padding click area ở mobile production |
| Icon action | 37×37 | `.icon-btn` | Nên tăng hit area ≥44×44 trong production mobile |
| Text input / select / login input | cao 43; padding x 12; border 1; radius 9 | `.field input`, `.field select`, `.login-field` | Focus ring ngoài 3px; offset 3px |
| Search field | min-width 260; input height 40 | `.search-bar` | Nếu thiếu chỗ, full width ở mobile |
| Segmented control | padding 3; gap 3; button padding `7px 10px`; radius 10 (outer) | `.segmented` | Sáng/Tối |
| Toggle switch | 38×22, padding 3; knob 16 | `.switch` | Disabled cho SafeExit/replication/encryption chưa có |
| Pill | padding `7px 11px`; font 10/750; radius 999 | `.pill` | Không biểu đạt trạng thái chỉ bằng màu |
| Tag | padding `6px 9px`; radius 7; font 10 | `.tag` | Nhãn tĩnh |
| Card | fluid; radius 12; border 1 | `.card` | Body không cố định chiều cao |
| Card header | padding `16px 18px 14px`; gap 14 | `.card-header` | Mobile padding `16px 15px` |
| Card body | padding `0 18px 18px` | `.card-body` | Mobile `0 15px 16px` |
| Stats grid | 4 cột desktop, gap 14 | `.stats` | 2 cột ≤1100, gap 9 ≤560 |
| KPI tile | padding `19px 20px 17px`; border 1; radius 15 | `.stat-card` | Mobile padding 15 |
| KPI icon | 28×28, radius 9 | `.stat-icon` | Orange soft |
| KPI number | font 26/800 | `.stat-value` | Responsive theo token |
| Device cards | 3 cột desktop; grid gap 16 | `.device-grid` | 2 cột ≤1100; 1 cột ≤560 |
| Device card | padding 18; radius 14 | `.device-card` | Có selected border 1 |
| Device icon | 35×35 hoặc inline 43×43 ở thẻ máy | `.device-icon` | Vị trí cố định, không thay text |
| Peer check | 22×22, radius 7 | `.check-peer` | Bao bọc bởi button và aria-pressed |
| Send form | `1.1fr / minmax(290px,.72fr)`, gap 20 | `.form-grid` | 1 cột ≤850 |
| Send panel block | padding 21 | `.panel-block` | Tùy nội dung |
| Step number | 30×30, radius 9 | `.step-number` | Bước 1–3 |
| Drop zone | padding `32px 23px`; dashed border 1.5; radius 12 | `.dropzone` | Click, Enter, Space, drag/drop |
| Upload icon | 49×49, radius 13 | `.drop-icon` | Icon trong vùng chọn |
| File chip | padding `11px 13px`; gap 12; radius 11 | `.file-chip` | Tên file dài wrap |
| Recipient choose-row | padding 12; gap 11; radius 10 | `.choose-row` | Selected state |
| Settings grid | 2 cột, gap 20 | `.settings-grid` | 1 cột ≤850 |
| Login dialog | max-width 430; padding 29; radius 20 | `.auth-dialog` | `width:100%`, backdrop toàn màn |
| Toast | max-width 360; padding `13px 15px`; radius 11 | `.toast` | bottom 20/right 22 |
| File progress bar | height 5; radius 8; top margin 13 | `.progress-track` | 0–100 theo bytes received |
| History empty state | min-height 330; padding 25 | `.history-empty` | Không dùng để lấp dữ liệu |

**Cảnh báo về độ chính xác:** bảng trên phản ánh `styles.css` và token gốc. Một số `gap`, `margin`, `line-height` cục bộ vẫn là giá trị literal trong component CSS; chỉ thay literal khi muốn thay *component riêng* và đã review cả 2 theme.

## 4. Graph / topology node–edge (màn quan trọng nhất)

| Thuộc tính | Desktop (>1100) | Tablet (≤1100) | Mobile (≤560) |
|---|---|---|---|
| Canvas height | 354px | 354px | 320px |
| Canvas background dot grid | 22×22px | 22×22px | 22×22px |
| Node card width | 148px | 145px | 117px |
| Node min-height | 77px | 77px | 67px |
| Node padding | 10px | 10px | 7px |
| Node border-radius | 12px | 12px | 10px |
| Node internal progress height | 3px | 3px | 3px |
| Static edge stroke | 1.8px | 1.8px | 1.8px |
| Flow edge stroke | 2.3px | 2.3px | 2.3px |
| Active dash sequence | `7 9` | `7 9` | `7 9` |
| Animation | 1350ms linear infinite | same | same, reduced-motion disable |
| Node placement | A `(50%,17%)`, B `(25.5%,52%)`, C `(74.5%,52%)`, D `(50%,85%)` | same percentages | same percentages |

**Sơ đồ A/B/C/D là một scenario minh họa của tài liệu nguồn.** Các tọa độ trên là `left/top` của tâm node theo phần trăm canvas (node `translate(-50%,-50%)`), không phải tọa độ mạng hoặc vị trí thực. Edge SVG nằm trên `viewBox="0 0 900 430"` và `preserveAspectRatio="none"`: chỉ phù hợp topology demo 4 nút. Không dùng nguyên cách vẽ này cho 5+ nút hoặc cho đồ thị nhiều cạnh.

**Đề xuất khi port vào production (không tự ý thêm thư viện):** ở 1–4 peers dùng layout cố định hoặc SVG; với 5–25 peers dùng layout graph có pan/zoom/minimap hoặc grouped LAN cluster; nhiều hơn 25 peers cần list + aggregate cluster, không cố nhét mọi node lên 376px. Tất cả phải có list fallback cho keyboard và screen reader.

**Semantics line:** orange dashed `assignment active` (chỉ khi có assignment backend thực), blue dashed `measured LAN`, gray dashed `candidate/unknown`, red offline/error. Hiển thị line-type bằng text. Không lấy tốc độ dash làm đo tốc độ truyền. Phân biệt `RECIEVED` [sic] trong UI nếu có lỗi chính tả; coding agent phải dùng đúng `RECEIVED` trong model.

## 5. Responsive acceptance / không được sai layout

- 320/390/560/768/1024/1280/1440px: không được có horizontal page overflow; dropdown/text phải wrap, không che CTA.
- ≤850px: sidebar overlay có scrim, mở/đóng được bằng touch và keyboard; content nhận full width, topbar chỉ 65px.
- Graph 390px: tất cả node có thể focus, không trùng node và flow labels vẫn đọc được. Với nhiều peer, dùng pan/zoom hoặc list fallback, không thu node xuống nhỏ hơn 117px.
- Font và touch target: reference UI có nhãn 10/11px và icon control 37px. Đây **chưa là bản accessibility-ready**; production cần nâng các nhãn và tap target theo WCAG/định hướng nền tảng trước khi phát hành.
- Trạng thái mạng: offline/stale khác paused; không tiếp tục chuyển động khi không có telemetry thật.
- Theme: màu text/border/background phải đổi đồng bộ; trạng thái verified phải đi kèm chữ và icon.

## 6. Component map để agent sửa nhanh

| Yêu cầu chỉnh sửa | Sửa ở đâu |
|---|---|
| Thay màu cam chủ đạo | `tokens.css` → `--rt-brand-500`, `--rt-brand-400`; kiểm tra đồng bộ `--accent-soft` |
| Đổi kích thước sidebar | `tokens.css` → `--rt-sidebar-width`; media query `max-width:1300px`, `max-width:850px` trong `styles.css` |
| Đổi font / size | `tokens.css` → `--rt-font-*`; `styles.css` nơi đặt `font-size` đặc biệt |
| Đổi độ cao graph | `tokens.css` → `--rt-graph-height`; override `@media (max-width:560px)` |
| Đổi kích thước node | `tokens.css` → `--rt-graph-node-*`; tablet/mobile overrides trong `styles.css` |
| Đổi số cột Card/Grid | `.stats`, `.split`, `.device-grid`, `.settings-grid` trong `styles.css` |
| Đổi nội dung từng màn | `overview()`, `peersPage()`, `sendPage()`, `transferPage()`, `historyPage()`, `settingsPage()` trong `app.js` |
| Đổi logic mô phỏng | `makeJob()`, `netDiagram()`, `tickSimulation()`, `startJob()` trong `app.js` |
| Đổi trạng thái thực | **Không sửa simulator để giả dữ liệu thực.** Thay adapter sau khi có API contract được duyệt |



## Bổ sung kích thước và hành vi UI v1.2 (ưu tiên hơn các snapshot cũ nếu có xung đột)

| Thành phần | Kích thước canonical mới | Ghi chú |
|---|---|---|
| Logo sidebar | 54×42px | logo sóc gốc, `object-fit:contain`, không shadow |
| Logo dialog | 92×68px | logo sóc, không đổ bóng |
| Icon line | viewBox 24×24; 1.85px stroke | rounded cap/join; sidebar hiển thị 19px |
| Sidebar desktop | 244px | compact 220px; off-canvas 240px |
| Navigation item | 42px high | padding ngang 12px, gap 12px |
| Topbar desktop | min-height 64px | tablet/mobile theo media rules 65px |
| Main content | padding 24px 30px 36px | tablet ≤850: 22px 20px; mobile ≤560: 18px 14px |
| Page header | bottom margin 20px | không eyebrow hoặc mô tả dài |
| Card | radius 12px | 1px border, no shadow |
| Card header | 16px 18px 14px | khoảng cách gọn |
| Card body | 0 18px 18px | — |
| Grid gap | 16px | các khu vực chính |
| Graph canvas | 354px desktop, 320px mobile | node vị trí theo top/left % |
| Node | 148px width desktop, 117px mobile | không halo, viền nhấn bằng brand 500 |
| Focus outline | 3px, offset 3px (global), graph node 2px | không loại bỏ focus indicator |

**Quy tắc thị giác:** Không dùng `box-shadow`, `filter:drop-shadow`, `backdrop-filter:blur`, neon, màu cam phát sáng. Chỉ hiển thị một nhãn DEMO toàn cục; status trên peer giữ chữ ngắn nhưng phân biệt `đã nhận` và `đã xác minh`. Các thông số trên là **chỉ dẫn thiết kế UI**, không phải ràng buộc từ sản phẩm Croc.
