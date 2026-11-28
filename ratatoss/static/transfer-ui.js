/* Classic script so the same renderers can run from a local file or loopback. */
(() => {
  "use strict";

  const number = new Intl.NumberFormat("vi-VN");
  const offerStates = {
    PENDING: "Chờ quyết định",
    ACCEPTED: "Đã chấp nhận",
    DECLINED: "Đã từ chối",
    EXPIRED: "Đã hết hạn",
    REVOKED: "Đã thu hồi",
  };
  const connections = {
    peer_offline: "Mất kết nối máy",
    controller_offline: "Mất kết nối điều phối",
    waiting_source: "Chờ nguồn có batch",
  };
  const activities = {
    downloading: "Đang tải",
    verifying: "Đang kiểm",
    forwarding: "Đang chuyển tiếp",
    assembling: "Đang ghép",
  };

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function field(list, label, value) {
    const row = element("div", "rt-transfer-field");
    const detail = element("dd", "rt-transfer-value");
    detail.append(value);
    row.append(element("dt", "rt-transfer-label", label), detail);
    list.append(row);
  }

  function button(label, focusKey, handler, primary = false) {
    const control = element("button", primary
      ? "rt-transfer-button rt-transfer-primary" : "rt-transfer-button", label);
    control.type = "button";
    control.dataset.transferFocus = focusKey;
    control.addEventListener("click", handler);
    return control;
  }

  function emit(root, eventName, detail) {
    root.dispatchEvent(new CustomEvent(eventName, { bubbles: true, detail }));
  }

  function card(title, status, tone) {
    const content = element("div", "rt-transfer-card");
    const header = element("div", "rt-transfer-card-header");
    const heading = element("h2", "rt-transfer-heading", title);
    heading.tabIndex = -1;
    heading.dataset.transferFocus = "heading";
    header.append(heading);
    if (status) {
      header.append(element("p", `rt-transfer-status rt-transfer-${tone}`, status));
    }
    content.append(header);
    return content;
  }

  function replaceView(root, content, announcement, retainedControls = null) {
    const active = document.activeElement;
    const hadFocus = root.contains(active);
    const focusKey = active?.dataset.transferFocus;
    const previous = root.firstElementChild;
    const sameItem = previous?.dataset.offerId === content.dataset.offerId;
    let live = root.querySelector(":scope > .rt-transfer-live");
    if (retainedControls) {
      // Keep the controls mounted so a native modal and its focus stay intact.
      for (const child of [...previous.children]) {
        if (child !== retainedControls) child.remove();
      }
      retainedControls.before(...content.children);
    } else if (live) {
      previous.querySelector("dialog[open]")?.close();
      previous.replaceWith(content);
    } else {
      live = element("div", "rt-transfer-live");
      live.setAttribute("aria-live", "polite");
      live.setAttribute("aria-atomic", "true");
      root.replaceChildren(content, live);
    }
    if (live.textContent !== announcement) live.textContent = announcement;
    if (hadFocus && !root.contains(active)) {
      const controls = [...root.firstElementChild.querySelectorAll("[data-transfer-focus]")];
      const target = sameItem ? controls.find((control) => control.dataset.transferFocus === focusKey
        && !control.closest("dialog:not([open])")) : null;
      (target ?? controls[0]).focus({ preventScroll: true });
    }
  }

  function offerDeadline(iso) {
    const timestamp = new Date(iso);
    if (Number.isNaN(timestamp.valueOf())) return "Chưa rõ thời hạn";
    const time = element("time", "", timestamp.toLocaleString("vi-VN", {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit",
      minute: "2-digit", timeZoneName: "short",
    }));
    time.dateTime = iso;
    return time;
  }

  function consentControls(root, offerId) {
    const group = element("div", "rt-transfer-consent");
    const label = element("label", "rt-transfer-forward");
    const forward = element("input", "rt-transfer-checkbox");
    forward.type = "checkbox";
    forward.dataset.transferFocus = "forward";
    label.append(forward, "Cho phép chuyển tiếp trong lượt gửi này");

    const actions = element("div", "rt-transfer-actions");
    const decide = (decision) => emit(root, "ratatoss:offer-decision", {
      offer_id: offerId, decision, allow_forward: decision === "ACCEPT" && forward.checked,
    });
    actions.append(
      button("Chấp nhận", "accept", () => decide("ACCEPT"), true),
      button("Từ chối", "decline", () => decide("DECLINE")),
    );
    group.append(label, actions);
    return group;
  }

  function withdrawControls(root, offerId) {
    const actions = element("div", "rt-transfer-actions");
    const dialog = element("dialog", "rt-transfer-dialog");
    dialog.setAttribute("aria-label", "Rút khỏi lượt gửi");
    const trigger = button("Rút khỏi lượt gửi", "withdraw", () => {
      trigger.focus({ preventScroll: true });
      dialog.showModal();
    });
    const cancel = button("Quay lại", "cancel-withdraw", () => dialog.close());
    cancel.autofocus = true;
    const confirm = button("Xác nhận rút", "confirm-withdraw", () => {
      dialog.close();
      emit(root, "ratatoss:offer-withdraw", { offer_id: offerId });
    });
    const choices = element("div", "rt-transfer-actions");
    choices.append(cancel, confirm);
    dialog.append(element("p", "rt-transfer-note", "Rút khỏi lượt gửi sẽ dừng tải và chuyển tiếp."),
      choices);
    actions.append(trigger, dialog);
    return actions;
  }

  function renderOffer(root, view) {
    const actionable = view.state === "PENDING" || view.state === "ACCEPTED";
    const sending = actionable && view.ui === "sending";
    const error = actionable && view.ui === "error";
    const status = sending ? "Đang gửi xác nhận"
      : error ? "Gửi xác nhận chưa thành công" : offerStates[view.state];
    const tone = error || view.state === "REVOKED" ? "danger"
      : view.state === "EXPIRED" ? "warning" : "neutral";
    const content = card("Nhận", status, tone);
    content.dataset.offerId = view.offer_id;
    const details = element("dl", "rt-transfer-details");
    field(details, "Tệp", view.file_name);
    field(details, "Người gửi", view.source_name);
    field(details, "Dung lượng", `${number.format(view.size_bytes)} byte`);
    field(details, "Thời hạn", offerDeadline(view.expires_at));
    field(details, "Vị trí lưu", view.save_location ?? "Chưa chọn vị trí lưu");
    content.append(details);

    if (view.reason) content.append(element("p", "rt-transfer-note", view.reason));
    let retainedControls = null;
    if (actionable && !sending && view.can_act !== false) {
      const previous = root.firstElementChild;
      const existing = previous?.lastElementChild;
      if (previous?.dataset.offerId === view.offer_id
          && existing?.dataset.offerAction === view.state) {
        retainedControls = existing;
      }
      const controls = retainedControls ?? (view.state === "PENDING"
        ? consentControls(root, view.offer_id) : withdrawControls(root, view.offer_id));
      if (view.state === "PENDING") {
        // The default follows the snapshot. Native checkbox edits keep their value.
        controls.querySelector(".rt-transfer-checkbox").defaultChecked = view.allow_forward === true;
      }
      if (!retainedControls) {
        controls.dataset.offerAction = view.state;
        content.append(controls);
      }
    }
    replaceView(root, content, [status, view.reason].filter(Boolean).join(". "), retainedControls);
  }

  function etaText(eta) {
    if (eta === "estimating") return "Đang ước tính";
    if (eta === null) return null;
    const seconds = Math.ceil(eta / 1000);
    if (seconds < 60) return `Còn khoảng ${number.format(seconds)} giây`;
    return `Còn khoảng ${number.format(Math.ceil(seconds / 60))} phút`;
  }

  function progressMeter(view) {
    const meter = element("div", "rt-transfer-meter");
    const label = element("p", "rt-transfer-label", "Byte đã xác minh");
    const count = `${number.format(view.verified_bytes)} / ${number.format(view.total_bytes)} byte`;
    const progress = element("progress", "rt-transfer-progress", count);
    progress.max = view.total_bytes || 1;
    progress.value = view.total_bytes === 0 ? Number(view.file_verified) : view.verified_bytes;
    progress.setAttribute("aria-label", label.textContent);
    progress.setAttribute("aria-valuetext", count);
    meter.append(label, element("p", "rt-transfer-count", count), progress);
    return meter;
  }

  function partialRecipients(recipients) {
    const summary = element("div", "rt-transfer-recipient-summary");
    const verified = recipients.filter((recipient) => recipient.file_verified).length;
    const count = `${number.format(verified)} / ${number.format(recipients.length)} đích xác minh`;
    summary.append(element("p", "rt-transfer-note", count));
    const list = element("ul", "rt-transfer-recipient-list");
    for (const recipient of recipients) {
      if (recipient.file_verified) continue;
      const message = recipient.reason ?? "Chưa xác minh";
      list.append(element("li", "rt-transfer-recipient", `${recipient.device_name} · ${message}`));
    }
    summary.append(list);
    return summary;
  }

  function renderProgress(root, view) {
    const outcome = view.outcome === "partial" ? "Hoàn tất một phần"
      : view.outcome === "complete" && view.file_verified ? "Hoàn tất"
      : view.outcome === "open" && view.connection === "peer_offline" ? "Đang chờ" : null;
    const content = card("Tiến độ", outcome, view.outcome === "complete" ? "success" : "warning");
    content.append(progressMeter(view));

    const messages = element("ul", "rt-transfer-messages");
    const announcement = [outcome];
    const report = (text, tone = "neutral") => {
      if (!text) return;
      messages.append(element("li", `rt-transfer-message rt-transfer-${tone}`, text));
      announcement.push(text);
    };
    report(connections[view.connection], view.connection === "waiting_source" ? "warning" : "danger");
    if (view.rechecking) report("Đang kiểm tra dữ liệu đã lưu");
    for (const activity of view.activity) report(activities[activity]);
    if (view.file_verified) {
      report("Đã xác minh", "success");
      if (view.receipt === "pending") report("Đã lưu trên máy · chờ báo người gửi");
    }
    if (messages.childElementCount) content.append(messages);
    const eta = etaText(view.eta);
    if (eta) content.append(element("p", "rt-transfer-note", eta));
    if (view.eta === "estimating") announcement.push(eta);
    if (view.file_verified && view.location) {
      const details = element("dl", "rt-transfer-details");
      field(details, "Vị trí tệp", view.location);
      content.append(details);
    }
    if (view.outcome === "partial" && view.recipient_results?.length) {
      content.append(partialRecipients(view.recipient_results));
    }
    replaceView(root, content, announcement.filter(Boolean).join(". "));
  }

  window.RatatossTransferUI = Object.freeze({ renderOffer, renderProgress });
})();
