# Ratatoss UI — Changelog v1.2 (18/11/2026)

## Các điều chỉnh theo phản hồi mới nhất

- Logo: thay hoàn toàn logo R tạm bằng logo sóc chính thức được cung cấp. Đính kèm `assets/ratatoss-logo-original.png` nguyên gốc, `assets/ratatoss-logo.webp` phiên bản web, `assets/ratatoss-favicon.png`.
- Style: loại bỏ toàn bộ glow, halo, shadow trang trí, blur nền modal; các thành phần phẳng với border 1px.
- Icons: thay icon luồng truyền bằng node-connection đơn giản; thay gear cài đặt bằng hình cân đối; chuẩn SVG outline viewBox `24×24`, nét `1.85px`, round cap/join; nav 19px.
- Dashboard: bốn KPI, sơ đồ node–edge, tiến độ nhận — bỏ nguyên tắc phân phối và microcopy lặp.
- Toàn UI: tiêu đề ngắn, bỏ eyebrow song ngữ, giảm chú thích không thiết yếu, giữ badge DEMO nhìn thấy trên desktop và mobile.
- Settings: giữ feature gates SafeExit, sao lưu dự phòng tự động và encryption xuyên hop ở trạng thái chưa khả dụng — KHÔNG tự cho rằng backend đã có.
- Prototype: HTML standalone nhúng logo WebP + favicon, chạy offline. Source tách `index.html` / `tokens.css` / `styles.css` / `app.js` để chỉnh sửa.

## Mốc kích thước đã thống nhất

`--rt-brand-500: #f47a28`; sidebar desktop 244px, compact 220px, mobile drawer 240px; topbar 64px desktop, 65px mobile; logo 54×42px sidebar; nav 42px; 19px icons; card radius 12px; grid gap 16px; main padding desktop 24px/30px/36px; mobile 18px/14px/40px; graph 354px desktop, 320px mobile; node 148px desktop, 117px mobile. Xem đầy đủ `DESIGN_TOKENS.md` + `COMPONENT_DIMENSIONS.md` và `../tokens.css`.

## Nguồn kỹ thuật và giới hạn không thay đổi

Brief v1.2 bất biến. Gửi/nhận Croc thật, peer discovery thật, ETA/goodput thật, authentication, metrics và audit chưa có trong prototype. Mock không phải benchmark. Phân biệt received với verified; SafeExit và blanket replication không được bật mặc định. Coding agent không được tự suy diễn API hoặc đổi kiến trúc.

## Kiểm tra

Xem `QA_REPORT_v1.2.md`. 45/45 kiểm tra DOM tương tác/overflow/brand/theme/module đã đạt. Đây không thay thế kiểm thử tích hợp và đánh giá accessibility khi build production.
