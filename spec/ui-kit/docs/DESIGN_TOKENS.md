# Ratatoss — Design Tokens (đầy đủ, đồng bộ mã nguồn)

**Mã tài liệu:** `RAT-UI-TOKENS-001` · **v1.1.0** · 18/11/2026 · **Trạng thái:** Bản đề xuất UI, không phải yêu cầu thuật toán.

**Nguồn chính xác:** [`../tokens.css`](../tokens.css). File JSON máy đọc: [`../design-tokens.json`](../design-tokens.json). `styles.css` phải được load **sau** `tokens.css`. Chỉnh một token ở đây sẽ ảnh hưởng các component cùng sử dụng; chỉ cần sửa `styles.css` nếu thay đổi bố cục riêng một component.

## 1. Quy ước và hướng dẫn chỉnh sửa

- `--rt-brand-*`: dải màu cam **định danh**; `--accent` là alias được dùng bởi prototype. Không thay đổi brand 500 cho một component đơn lẻ.
- `--bg`, `--panel`, `--text`, `--stroke`… là **semantic theme tokens** của dark/light. Luôn dùng semantic trong component, không ghi trực tiếp mã hex khi có token tương đương.
- Kích thước dùng **CSS px ở 100% browser zoom**. Breakpoint nằm trong `@media` của `styles.css` vì CSS media queries không dùng được biến `var()` như điều kiện.
- Font demo có fallback hệ thống; không đóng gói font bản quyền. Chỉ thêm/self-host font đã được phép sử dụng.
- `--rt-*` là token canonical. Các alias cũ (`--accent`, `--panel`…) được giữ để không phá file `styles.css` trước đó.
- Độ sáng dark/light đổi bằng `body[data-theme="dark|light"]`, `localStorage` chỉ lưu lựa chọn theme trên trình duyệt demo.

## 2. Bảng token toàn bộ (giá trị gốc đúng theo `tokens.css`)

### Thương hiệu và trạng thái

| Token | Giá trị CSS mặc định |
|---|---|
| `--rt-brand-50` | `#fff2e9` |
| `--rt-brand-100` | `#ffe4ce` |
| `--rt-brand-200` | `#ffc99d` |
| `--rt-brand-300` | `#ffac70` |
| `--rt-brand-400` | `#ff9d50` |
| `--rt-brand-500` | `#f47a28` |
| `--rt-brand-600` | `#da641d` |
| `--rt-brand-700` | `#ad4710` |
| `--rt-brand-800` | `#7f310b` |
| `--rt-brand-900` | `#4e200f` |
| `--rt-success-500` | `#49c899` |
| `--rt-info-500` | `#8baef9` |
| `--rt-warning-500` | `#ffc679` |
| `--rt-danger-500` | `#ee7b75` |

### Trung tính (neutral ramp)

| Token | Giá trị CSS mặc định |
|---|---|
| `--rt-dark-950` | `#0e1014` |
| `--rt-dark-900` | `#111318` |
| `--rt-dark-850` | `#14171d` |
| `--rt-dark-800` | `#171a20` |
| `--rt-dark-750` | `#1c2027` |
| `--rt-dark-700` | `#1d2027` |
| `--rt-dark-650` | `#24272e` |
| `--rt-dark-600` | `#252932` |
| `--rt-dark-500` | `#2c3038` |
| `--rt-light-0` | `#ffffff` |
| `--rt-light-50` | `#fbfaf8` |
| `--rt-light-100` | `#f6f5f2` |
| `--rt-light-150` | `#f1f1ef` |
| `--rt-light-200` | `#efefed` |
| `--rt-light-250` | `#e7e7e4` |

### Typography

| Token | Giá trị CSS mặc định |
|---|---|
| `--rt-font-family-body` | `"DM Sans", "Segoe UI", Arial, sans-serif` |
| `--rt-font-family-heading` | `"Manrope", "DM Sans", "Segoe UI", Arial, sans-serif` |
| `--rt-font-family-mono` | `ui-monospace, SFMono-Regular, Consolas, monospace` |
| `--rt-font-xxs` | `10px` |
| `--rt-font-xs` | `11px` |
| `--rt-font-sm` | `12px` |
| `--rt-font-md` | `13px` |
| `--rt-font-lg` | `14px` |
| `--rt-font-xl` | `16px` |
| `--rt-font-2xl` | `16px` |
| `--rt-font-3xl` | `18px` |
| `--rt-font-4xl` | `21px` |
| `--rt-font-5xl` | `23px` |
| `--rt-font-card-title` | `14px` |
| `--rt-font-kpi` | `26px` |
| `--rt-font-page-min` | `24px` |
| `--rt-font-page-max` | `33px` |
| `--rt-line-tight` | `1.24` |
| `--rt-line-body` | `1.58` |
| `--rt-line-relaxed` | `1.70` |
| `--rt-font-weight-regular` | `400` |
| `--rt-font-weight-medium` | `500` |
| `--rt-font-weight-semibold` | `600` |
| `--rt-font-weight-bold` | `700` |
| `--rt-font-weight-heavy` | `800` |

### Spacing

| Token | Giá trị CSS mặc định |
|---|---|
| `--rt-space-0` | `0px` |
| `--rt-space-1` | `4px` |
| `--rt-space-2` | `8px` |
| `--rt-space-3` | `12px` |
| `--rt-space-4` | `16px` |
| `--rt-space-5` | `20px` |
| `--rt-space-6` | `24px` |
| `--rt-space-8` | `32px` |
| `--rt-space-10` | `40px` |
| `--rt-space-12` | `48px` |
| `--rt-space-16` | `64px` |
| `--rt-space-legacy-5` | `5px` |
| `--rt-space-legacy-13` | `13px` |
| `--rt-space-legacy-18` | `18px` |

### Bo góc / viền / bóng

| Token | Giá trị CSS mặc định |
|---|---|
| `--rt-radius-none` | `0px` |
| `--rt-radius-xs` | `6px` |
| `--rt-radius-sm` | `9px` |
| `--rt-radius-md` | `9px` |
| `--rt-radius-lg` | `13px` |
| `--rt-radius-xl` | `20px` |
| `--rt-radius-pill` | `999px` |
| `--rt-card-radius` | `12px` |
| `--rt-graph-node-radius` | `12px` |
| `--rt-border-width` | `1px` |
| `--rt-border-dashed` | `1.5px` |
| `--rt-focus-width` | `3px` |
| `--rt-focus-offset` | `3px` |
| `--rt-shadow-node` | `none` |
| `--rt-shadow-dialog` | `none` |

### Shell / Layout

| Token | Giá trị CSS mặc định |
|---|---|
| `--rt-sidebar-width` | `244px` |
| `--rt-sidebar-padding-block` | `22px` |
| `--rt-sidebar-padding-inline` | `15px` |
| `--rt-sidebar-padding-bottom` | `17px` |
| `--rt-logo-size` | `52px` |
| `--rt-nav-item-height` | `42px` |
| `--rt-topbar-height` | `64px` |
| `--rt-content-max` | `1640px` |
| `--rt-content-inline` | `30px` |
| `--rt-content-top` | `24px` |
| `--rt-content-bottom` | `36px` |

### Thành phần UI

| Token | Giá trị CSS mặc định |
|---|---|
| `--rt-grid-gap` | `16px` |
| `--rt-card-header-padding` | `16px 18px 14px` |
| `--rt-card-body-padding` | `0 18px 18px` |
| `--rt-button-padding-y` | `11px` |
| `--rt-button-padding-x` | `16px` |
| `--rt-button-min-height` | `42px` |
| `--rt-button-sm-min-height` | `34px` |
| `--rt-icon-button-size` | `37px` |
| `--rt-field-height` | `43px` |
| `--rt-field-radius` | `9px` |
| `--rt-control-touch-target` | `44px` |
| `--rt-progress-height` | `5px` |
| `--rt-graph-height` | `354px` |
| `--rt-graph-node-width` | `148px` |
| `--rt-graph-node-min-height` | `77px` |
| `--rt-graph-node-progress-height` | `3px` |
| `--rt-graph-grid-step` | `22px` |
| `--rt-graph-stroke` | `1.8px` |
| `--rt-graph-active-stroke` | `2.3px` |
| `--rt-login-width` | `430px` |
| `--rt-dialog-padding` | `29px` |
| `--rt-dropzone-padding-block` | `32px` |
| `--rt-dropzone-padding-inline` | `23px` |
| `--rt-dropzone-radius` | `12px` |
| `--rt-device-icon-size` | `35px` |
| `--rt-peer-switch-width` | `38px` |
| `--rt-peer-switch-height` | `22px` |
| `--rt-peer-switch-knob` | `16px` |
| `--rt-transfer-summary-gap` | `18px` |

### Motion và breakpoint

| Token | Giá trị CSS mặc định |
|---|---|
| `--rt-motion-fast` | `120ms` |
| `--rt-motion-normal` | `180ms` |
| `--rt-motion-slow` | `240ms` |
| `--rt-motion-progress` | `550ms` |
| `--rt-motion-flow-loop` | `1350ms` |
| `--rt-easing-standard` | `ease` |
| `--rt-breakpoint-wide` | `1300px` |
| `--rt-breakpoint-compact` | `1100px` |
| `--rt-breakpoint-tablet` | `850px` |
| `--rt-breakpoint-mobile` | `560px` |

### Alias CSS legacy

| Token | Giá trị CSS mặc định |
|---|---|
| `--accent` | `var(--rt-brand-500)` |
| `--accent2` | `var(--rt-brand-400)` |
| `--accent-deep` | `var(--rt-brand-700)` |
| `--green` | `var(--rt-success-500)` |
| `--blue` | `var(--rt-info-500)` |
| `--yellow` | `var(--rt-warning-500)` |
| `--red` | `var(--rt-danger-500)` |
| `--white` | `var(--rt-light-0)` |
| `--accent-soft` | `rgba(244,122,40,.11)` |

### Các token gốc còn lại

| Token | Giá trị |
|---|---|

## 3. Semantic theme palette: hai chế độ (giá trị chính xác)

Các giá trị không nằm trong `:root` sẽ được override khi đổi `data-theme`. Chúng là nguồn tạo màu thực cho nền, panel, text, trạng thái và focus. `null` không phải màu.

| Token | Dark | Light |
|---|---|---|
| `--bg` | `#0e1014` | `#f6f5f2` |
| `--sidebar` | `#111318` | `#fbfaf8` |
| `--panel` | `#171a20` | `#ffffff` |
| `--panel-2` | `#1d2027` | `#f8f8f7` |
| `--panel-3` | `#252932` | `#efefed` |
| `--text` | `#f5f5f3` | `#22242a` |
| `--muted` | `#9399a6` | `#757a83` |
| `--muted2` | `#6d7380` | `#999da4` |
| `--stroke` | `#2c3038` | `#e7e7e4` |
| `--stroke-strong` | `#42464e` | `#d4d4d0` |
| `--shadow` | `none` | `0 14px 45px rgba(0,0,0,.09)` |
| `--graph` | `#14171d` | `#faf9f7` |
| `--chip` | `#24282f` | `#f1f1ef` |
| `--outline` | `#32343a` | `#e5e4e1` |
| `--input` | `#1c2027` | `#fbfaf8` |
| `--hover` | `#24272e` | `#f0efed` |
| `--orbon` | `#291b15` | `#fff2e9` |
| `--rt-accent-on-surface` | `#ff9d50` | `#a84410` |
| `--rt-on-accent` | `#20140e` | `#20140e` |
| `--rt-focus-color` | `rgba(244,122,40,.65)` | `rgba(173,71,16,.72)` |

## 4. Ràng buộc token để agent không tạo thiết kế lệch

1. **Orange First:** CTA chính `--accent`, hover `--accent2`; link LAN `--blue`; success verified `--green`; error/offline `--red`. Không thêm một màu brand thứ hai.
2. **Semantic tokens:** `--panel` phải phản ánh card, `--panel-2` là inset, `--graph` cho canvas topology; màu chỉ là biểu đạt phụ, luôn đi kèm trạng thái văn bản.
3. **Theme completeness:** khi thêm token theme phải có giá trị tương ứng trong cả dark và light, hoặc mặc định trong `:root` nếu thực sự dùng chung.
4. **No fixed-height text containers:** token height dành cho control, không áp cứng vào khối chứa text dài hoặc thông báo lỗi.
5. **Focus:** đảm bảo focus ring hiển thị ở cả theme. Mục tiêu production WCAG AA; font 10/11px trong concept là tham chiếu thị giác cần audit/tăng kích thước trước khi release.
6. **Motion:** chỉ vẽ luồng hoạt động nếu có sự kiện chuyển batch/assignment đáng tin cậy; tôn trọng `prefers-reduced-motion`. Không dùng tốc độ hoạt hình làm tốc độ mạng.
7. **File có hiệu lực:** `tokens.css` là canonical. `design-tokens.json` là snapshot để import vào design tooling; nếu thay token, chạy lại generator hoặc chỉnh JSON tương ứng và kiểm tra drift.

## 5. Công thức và ví dụ áp dụng

```css
/* Thay toàn bộ màu cam ứng dụng */
:root { --rt-brand-500: #f47a28; }
/* Lưu ý --accent alias đang trỏ vào brand-500. */

/* Thay độ cao thanh điều hướng desktop */
:root { --rt-nav-item-height: 43px; }

/* Mỗi card sử dụng semantic tokens: */
.custom-card {
  background: var(--panel);
  color: var(--text);
  border: var(--rt-border-width) solid var(--stroke);
  border-radius: var(--rt-card-radius);
  padding: var(--rt-space-5);
}
```

## 6. Lưu ý độ tương phản và khả năng mở rộng

- `#F47A28` làm màu nền CTA và đường flow. Trên light theme, chữ màu cam trên nền trắng nên dùng `--rt-accent-on-surface` tối hơn (đang có) trong component mới; rà soát các selector cũ sử dụng `--accent` cho text.
- 4 peer được đặt theo vị trí cố định để minh họa đúng scenario trong brief, **không phải quy tắc topology cho peer count lớn**. Nếu vượt 4 peer, phải thay bằng thuật toán layout có zoom/pan và fallback danh sách.
- Không suy đoán LAN/WAN từ màu. Loại link thực tế chỉ hiển thị khi Agent/Controller đo và xác minh.

**Tài liệu liên quan:** [`COMPONENT_DIMENSIONS.md`](./COMPONENT_DIMENSIONS.md) (kích thước theo màn), [`UI_SPEC.md`](./UI_SPEC.md) (nghiệp vụ và các trạng thái), [`SCREEN_BLUEPRINTS.md`](./SCREEN_BLUEPRINTS.md) (flow UI).


## Cập nhật 1.2 — Logo chính thức và thiết kế phẳng (18/11/2026)

**Quy tắc bắt buộc (ghi đè các nhận xét thẩm mỹ cũ):** Giao diện **không glow, không box-shadow bóng màu, không backdrop-blur, không gradient trang trí**, không halo ở node khi chọn. Dùng **border 1px** và thay đổi màu nền/viền để nhấn trạng thái; focus-visible phải giữ viền rõ. Bóng của dialog và node là `none`.

| Token mới/cập nhật | Giá trị | Sử dụng |
|---|---|---|
| `--rt-brand-500` | `#f47a28` | Orange primary |
| `--rt-logo-width` | `54px` | Logo trên sidebar desktop |
| `--rt-logo-height` | `42px` | Giữ tỷ lệ ảnh (object-fit: contain) |
| `--rt-icon-stroke` | `1.85px` | Độ đậm nét SVG thống nhất |
| `--rt-topbar-height` | `64px` | Topbar desktop |
| `--rt-sidebar-width` | `244px` | Desktop |
| `--rt-content-top` | `24px` | Content desktop |
| `--rt-content-inline` | `30px` | Content desktop |
| `--rt-content-bottom` | `36px` | Content desktop |
| `--rt-grid-gap` | `16px` | Khoảng cách chính giữa cards |
| `--rt-card-radius` | `12px` | Bo card |
| `--rt-graph-height` | `354px` | Graph desktop |
| `--rt-shadow-node` | `none` | Cấm shadow |
| `--rt-shadow-dialog` | `none` | Cấm shadow |

Nguồn logo: `assets/ratatoss-logo-original.png` (nguyên ảnh được cung cấp, **không đổi nội dung**), `assets/ratatoss-logo.webp` (bản tối ưu và crop transparent margins phục vụ UI), `assets/ratatoss-favicon.png`. Không dùng logo chữ R cũ. HTML standalone nhúng logo WebP dưới dạng data URI để hoạt động offline.

Responsive: tại viewport ≤850px, padding content ngang 20px và trên 22px; tại ≤560px, ngang 14px, trên 18px, canvas graph cao 320px và logo 49×38px. Những override breakpoint này nằm trong `styles.css`, không phải giá trị global.
