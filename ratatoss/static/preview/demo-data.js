/* Dữ liệu TỔNG HỢP cho trang DEMO. Các thao tác chỉ cập nhật giao diện mẫu. */
(() => {
  "use strict";

  const { renderOffer, renderProgress } = window.RatatossTransferUI;
  const fileName = "ratatoss-demo-32MiB.bin";
  const location = `Downloads/Ratatoss/${fileName}`;
  const total = 32 * 1024 * 1024;
  const offer = {
    offer_id: "demo-offer",
    source_name: "Máy Atlas",
    file_name: fileName,
    size_bytes: total,
    expires_at: "2027-01-01T12:00:00Z",
    save_location: location,
    state: "PENDING",
    ui: "idle",
    allow_forward: false,
    reason: null,
  };
  const progress = {
    job_id: "demo-job",
    total_bytes: total,
    verified_bytes: total / 2,
    activity: [],
    connection: "ok",
    rechecking: false,
    receipt: "pending",
    file_verified: false,
    location: null,
    eta: null,
    outcome: "open",
  };
  const offerCases = {
    pending: { label: "Chờ quyết định" },
    sending: { label: "Đang gửi xác nhận", ui: "sending" },
    expired: { label: "Đã hết hạn", state: "EXPIRED", reason: "Đã qua thời hạn trả lời." },
    revoked: { label: "Đã thu hồi", state: "REVOKED", reason: "Người gửi đã hủy lượt gửi." },
    accepted: { label: "Đã chấp nhận", state: "ACCEPTED" },
    declined: { label: "Đã từ chối", state: "DECLINED" },
    error: {
      label: "Gửi xác nhận lỗi", ui: "error", reason: "Chưa kết nối được với điều phối.",
    },
  };
  const progressCases = {
    downloading: { label: "Đang tải", activity: ["downloading"], eta: 42_000 },
    forwarding: { label: "Đang chuyển tiếp", activity: ["downloading", "forwarding"] },
    assembling: {
      label: "Đang ghép và kiểm", activity: ["assembling", "verifying"], verified_bytes: total,
    },
    peer_offline: { label: "Mất kết nối máy", connection: "peer_offline" },
    controller_offline: { label: "Mất kết nối điều phối", connection: "controller_offline" },
    waiting_source: { label: "Chờ nguồn có batch", connection: "waiting_source" },
    rechecking: {
      label: "Đang kiểm tra dữ liệu đã lưu", rechecking: true, verified_bytes: total / 4,
      eta: "estimating",
    },
    receipt_pending: {
      label: "Đã lưu trên máy · chờ báo người gửi", verified_bytes: total, file_verified: true,
      location,
    },
    verified: {
      label: "Đã xác minh", verified_bytes: total, receipt: "sent", file_verified: true,
      location, outcome: "complete",
    },
    partial: {
      label: "Hoàn tất một phần", verified_bytes: total, receipt: "sent", file_verified: true,
      location, outcome: "partial",
      recipient_results: [
        { device_name: "Máy Birch", file_verified: true },
        { device_name: "Máy Cypress", file_verified: true },
        { device_name: "Máy Dogwood", file_verified: false, reason: "Offer đã hết hạn" },
      ],
    },
  };
  const offerRoot = document.querySelector("#offer");
  const offerSelect = document.querySelector("#offer-case");

  function showCases(select, cases, base, root, render) {
    for (const [key, { label }] of Object.entries(cases)) {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = label;
      select.append(option);
    }
    const show = () => {
      const { label, ...changes } = cases[select.value];
      render(root, { ...base, ...changes });
    };
    select.addEventListener("change", show);
    show();
  }

  offerRoot.addEventListener("ratatoss:offer-decision", ({ detail }) => {
    offerSelect.value = "sending";
    renderOffer(offerRoot, { ...offer, ui: "sending", allow_forward: detail.allow_forward });
  });
  offerRoot.addEventListener("ratatoss:offer-withdraw", () => {
    offerSelect.value = "sending";
    renderOffer(offerRoot, {
      ...offer, state: "ACCEPTED", ui: "sending", reason: "Đang chờ xác nhận rút khỏi lượt gửi.",
    });
  });
  showCases(offerSelect, offerCases, offer, offerRoot, renderOffer);
  showCases(document.querySelector("#progress-case"), progressCases, progress,
    document.querySelector("#progress"), renderProgress);
})();
