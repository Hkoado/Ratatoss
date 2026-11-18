# Ratatoss — UI Kit HTML / CSS Tokens / Agent Handoff

**Version 1.2.0** · 18/11/2026 · **Prototype-only** · Tiếng Việt · Không cần npm/Node/Docker để mở giao diện.

Bộ UI cho **Ratatoss — ứng dụng phân phối 1 file P2P tới nhiều peer dựa trên Croc**. Thiết kế màu chủ đạo **cam `#F47A28`**, tối giản, hỗ trợ **dark/light**. Bám Product Brief v1.2, đặc biệt pipeline theo batch đã xác minh, makespan và phục hồi khi peer offline. Không bật mặc định SafeExit/nhân bản dự phòng.

> **Lưu ý:** Đây là **mock UI**, không có Croc, FastAPI Controller, peer discovery, xác thực, chuyển dữ liệu, băm file, benchmark hoặc tuyến mạng thật. Mọi node, thông lượng, trạng thái mô phỏng đều chỉ để đánh giá UX. Chọn file trong demo chỉ lấy tên và dung lượng, **không đọc/gửi nội dung file**.

## 1. Mở demo ngay

- **Mở một file duy nhất:** `Ratatoss_UI_Preview.html` (có sẵn toàn bộ CSS + JS + ảnh sóc, mở offline trong trình duyệt). File này là **bản build**, không phải nơi khuyến nghị sửa trực tiếp.
- **Sửa được, rõ ràng nhất:** mở `index.html` (giữ cùng thư mục với `tokens.css`, `styles.css`, `app.js`, `assets`). Dùng VS Code Live Server nếu trình duyệt hạn chế `file://`; không cần backend.
- **Xem bảng màu/kích thước:** `styleguide.html` (gallery thiết kế, đọc trực tiếp từ CSS tokens).

**Thử luồng:** Tổng quan → Thiết bị (chọn B/C/D) → Gửi tệp (chọn tên file) → Khởi chạy **mô phỏng** → Luồng truyền (click node, pause, giả lập C offline rồi online) → Lịch sử → Cài đặt (switch dark/light). Bấm avatar để xem màn hình đăng nhập demo.

## 2. Muốn chỉnh giao diện, sửa file nào?

| Thứ cần sửa | File canonical | Ví dụ |
|---|---|---|
| Màu cam, dark/light, font, spacing, radius, shell | **`tokens.css`** | `--rt-brand-500`, `--rt-sidebar-width`, `--rt-graph-node-width` |
| CSS component, hover, responsive, animation | **`styles.css`** | `.graph-node`, `.device-card`, `@media` |
| HTML từng trang, nhãn nút, icon, giả lập | **`app.js`** | `overview()`, `sendPage()`, `netDiagram()`, `settingsPage()` |
| Shell + thứ tự tải CSS | **`index.html`** | Load `tokens.css` trước `styles.css` |
| Bảng token tự đọc máy / design tools | `design-tokens.json` | Đồng bộ khi thay `tokens.css` |
| Logo sóc đã duyệt | `assets/ratatoss-logo.webp` | Bản web tối ưu, gốc lưu tại `assets/ratatoss-logo-original.png` |
| Bản HTML gộp để chia sẻ | `Ratatoss_UI_Preview.html` | Được build lại sau khi sửa source, không sửa riêng |

**Đồng bộ standalone:** sau khi chỉnh source `tokens.css` / `styles.css` / `app.js`, chạy `python scripts/build_preview.py` từ thư mục `Ratatoss_UI_Kit`. Python chỉ dùng để đóng gói; **không cần cài thư viện**. Có thể tự mở `index.html` để xem ngay, không bắt buộc build.

## 3. Tài liệu bàn giao dành cho coding agent — thứ tự đọc

1. `docs/SOURCE_RATATOSS_BRIEF_v1.2.md` — **bản gốc bất biến**, source of truth.
2. `docs/UI_SPEC.md` — mô tả UI/UX, screens, semantic trạng thái, feature gates và ranh giới API.
3. `docs/SCREEN_BLUEPRINTS.md` — cấu trúc từng màn + hành vi + empty/loading/error/stale/offline.
4. **`docs/DESIGN_TOKENS.md`** — **toàn bộ token CSS** và giá trị dark/light.
5. **`docs/COMPONENT_DIMENSIONS.md`** — **mọi kích thước component chính** và responsive breakpoints.
6. `docs/FRONTEND_CONTRACTS.ts` — **frontend view model đề xuất**, không phải API backend đã phê duyệt.
7. `docs/AGENT_HANDOFF.md` — prompt Astra (plan) / Sol (code), quy tắc cấm đoán và acceptance.

## 4. Cấu trúc gói

```text
Ratatoss_UI_Kit/
├── index.html                    # file khởi chạy có thể sửa trực tiếp
├── tokens.css                    # ALL canonical CSS tokens + dark/light themes
├── styles.css                    # CSS component + responsive
├── app.js                        # Vanilla JS screens and UI mock interactions
├── styleguide.html               # token + component visual gallery
├── design-tokens.json            # machine-readable snapshot của tokens.css
├── Ratatoss_UI_Preview.html      # một HTML duy nhất, gộp từ source
├── assets/ratatoss-logo-original.png  # ảnh sóc nguyên gốc được cung cấp
├── assets/ratatoss-logo.webp          # logo đã crop viền + nén, nền trong suốt
├── assets/ratatoss-favicon.png        # favicon sóc
├── scripts/build_preview.py      # đóng gói HTML standalone + đồng bộ JSON
└── docs/
    ├── SOURCE_RATATOSS_BRIEF_v1.2.md  # DO NOT MODIFY
    ├── UI_SPEC.md
    ├── SCREEN_BLUEPRINTS.md
    ├── DESIGN_TOKENS.md
    ├── COMPONENT_DIMENSIONS.md
    ├── FRONTEND_CONTRACTS.ts
    └── AGENT_HANDOFF.md
```

## 5. Giới hạn tính năng demo / yêu cầu production

- Demo có **1 job mẫu 20 GB đang chạy**, 4 peer mẫu (A nguồn; B/C cùng LAN; D remote), và bộ đếm giả lập 1.8s/nhịp. Tốc độ phần trăm **không phải goodput thực**.
- Khi mới tạo phiên, file được chọn chỉ là **metadata**. Backend cần một thiết kế riêng cho file handoff đến Agent trước khi Croc có thể truyền thật.
- Login demo chỉ lưu hồ sơ trong RAM. Người dùng **không được nhập mật khẩu thật**; human auth không được Brief v1.2 đặc tả.
- Cấu hình giới hạn RX/TX và băng thông chỉ là form demo, không được áp vào Agent.
- Trạng thái verified file, peer WAN/LAN và topology chỉ được tin khi backend trả dữ liệu được xác thực; UI không được tự suy từ animation.
- Để port production cần API Contracts thực, error handling, focus/accessibility audit, responsive large peer count và integration tests.

## 6. Kiểm thử nhanh

- `node --check app.js` nếu có Node (không bắt buộc để dùng demo).
- `python scripts/build_preview.py --check` để kiểm tra biến CSS tham chiếu có định nghĩa, source brief còn bất biến tương đối với bản dùng xây UI, token snapshot khớp và standalone đã cập nhật.
- Browser QA: Dark/Light; màn 1440, 1280, 768, 390, 320px; peer selector; file picker; C offline/recover; keyboard Escape login; responsive menu; reduced-motion. Không tự nhận “đã đạt WCAG AA” chỉ nhờ kiểm tra screenshot.

**Nếu muốn triển khai web thực:** dùng HTML như *visual target* và `FRONTEND_CONTRACTS.ts` làm model UX; không dùng trực tiếp mock timer để dẫn động thuật toán PLARS.


## 7. Bản cập nhật v1.2 — giao diện gọn và logo sóc

- **Đã sử dụng logo sóc cam** được gửi trong cuộc trò chuyện cho sidebar, dialog đăng nhập, favicon và trang Token Lab. Logo nguyên bản được giữ nguyên trong bộ assets; bản WebP chỉ cắt khoảng trong suốt/nén để hiển thị nhanh.
- **Đã bỏ glow/shadow/decorative blur** của logo, card, node, popup; node selected dùng đường viền cam.
- **Đã vẽ lại icon `Cài đặt` và `Luồng truyền`**, đồng nhất stroke `1.85px`, viewBox 24×24 và round caps; sidebar icon hiển thị ở 19px.
- **Đã rút gọn dashboard và các màn khác**, bỏ eyebrow/banners/mô tả lặp; giữ badge DEMO cố định.
- Mở `Ratatoss_UI_Preview.html` để xem ngay (logo đã embedded, offline). Muốn chỉnh component: mở `index.html` cùng CSS/JS/assets.
- Tài liệu thay đổi: `docs/UI_SPEC.md`, `docs/DESIGN_TOKENS.md`, `docs/COMPONENT_DIMENSIONS.md`, `docs/SCREEN_BLUEPRINTS.md`, `docs/AGENT_HANDOFF.md`.

> Dữ liệu truyền, node, tuyến A/B/C/D, đăng nhập và trạng thái verified trong demo đều là mô phỏng. Việc đơn giản hóa copy **không** thay đổi giới hạn backend hoặc mục tiêu nghiên cứu Ratatoss.
