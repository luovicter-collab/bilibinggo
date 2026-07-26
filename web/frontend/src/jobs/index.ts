// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { fetchJSON } from "../api/client";
import { isLlmConfigured, requireSetup, scrollToLlmSettings, syncProjectState } from "../account/index";
import { buildActivityFilterJobParams, loadActivities, loadSummary, renderTripleParticipateBar } from "../activities/index";
import { ACTION_LABELS, COMMENT_OPTIONAL_PATTERNS, FORWARD_REQUIRED_ACTIONS, INTERACT_REQUIRED_ACTIONS, JOB_RESULT_AUTO_DISMISS_MS, JOB_RESULT_EXIT_MS, PARTICIPATE_ACTIVE_KEYWORDS, PARTICIPATE_DONE_KEYWORDS, PARTICIPATE_FAIL_KEYWORDS, PARTICIPATE_PENDING_KEYWORDS, PARTICIPATE_STEP_LABELS, REFRESH_ALL_DS_COUNT, REFRESH_ALL_PIPELINE, REFRESH_ALL_PIPELINE_SUBSTEPS, REFRESH_WATCH_PIPELINE, RESERVE_REQUIRED_ACTIONS, RESERVE_STEP_LABELS, SYNC_TOAST_ACTIONS, jobLog, jobMessage, jobResultActions, jobResultBanner, jobResultBody, jobResultEyebrow, jobResultHint, jobResultIcon, jobResultProgress, jobResultSummary, jobResultTitle, logDock, logDockBadge, logDockPanel, logDockToggle, progressBanner, progressChip, progressDetail, progressFill, progressFillGlow, progressLabel, progressPercent, progressPercentSuffix, progressRing, progressSteps, progressTrack, qrcodeClose, qrcodeFrame, qrcodeImg, qrcodeModal, qrcodeOverlay, qrcodeOverlayIcon, qrcodeOverlayText, qrcodeStatus, qrcodeTitle, sidebarLoginBtn } from "../dom";
import { startRealtime } from "../realtime/sse";
import { confirmRefreshAll } from "../shell/confirm";
import { switchSection } from "../shell/nav";
import { dismissRunningToasts, showToast } from "../shell/toast";
import { formatJobProgressDisplay, formatProgressDetail, formatProgressTitle, formatToastDetail } from "../utils/format";
import { clearActionButtonLoading, flashActivityRows, flashSourceRow, prefersReducedMotion, pulseWatchSyncCard, setButtonLoading, setSourceRowUpdating } from "../utils/motion";
import { escapeHtml, sanitizeUserText, truncateText } from "../utils/text";
import { loadWatchUsers } from "../watch/index";

let qrcodeLastFocus = null;

export function isRefreshPipelineAction(action) {
  return action === "refresh_all" || action === "refresh_source";
}

export function buildFailureContext(message, action, log = "") {
  const parts = [message, log].map((item) => sanitizeUserText(String(item || ""))).filter(Boolean);
  const text = parts.join("\n");
  return { text, lowered: text.toLowerCase(), action: String(action || "") };
}

export function classifyFailureText(message, action, log = "") {
  const { text, lowered, action: actionName } = buildFailureContext(message, action, log);
  const displayMessage = sanitizeUserText(message) || sanitizeUserText(log) || "操作失败，请稍后重试";

  if (/无可参与|没有可参与|已跳过/.test(text)) {
    return {
      kind: "empty",
      severity: "info",
      title: "提示",
      message: displayMessage,
      hint: "",
      actions: [],
      retryable: false,
    };
  }
  if (/已取消扫码|取消扫码登录|任务已取消/.test(text)) {
    return {
      kind: "cancelled",
      severity: "info",
      title: "提示",
      message: displayMessage,
      hint: "",
      actions: [],
      retryable: false,
    };
  }
  if (actionName === "login" || /二维码|扫码登录|sessdata|确认超时|登录未完成/.test(lowered)) {
    return {
      kind: "login",
      severity: "error",
      title: "登录未完成",
      message: displayMessage,
      hint: "请重新发起扫码登录，并在手机上确认。",
      actions: [{ id: "login", label: "重新扫码" }],
      retryable: true,
    };
  }
  if (/cookie|未登录|请先扫码|登录失效|重新扫码登录|未检测到有效登录/.test(lowered)) {
    return {
      kind: "auth",
      severity: "error",
      title: "需要登录",
      message: displayMessage,
      hint: "本地登录状态已失效，请重新扫码。",
      actions: [{ id: "login", label: "去登录" }],
      retryable: true,
    };
  }
  if (/llm|未配置|连接测试|api key|模型名称|无法连接 llm/.test(lowered)) {
    return {
      kind: "llm",
      severity: "error",
      title: "LLM 未就绪",
      message: displayMessage,
      hint: "在概览页填写 API Key 与模型名称，保存并通过连接测试。",
      actions: [{ id: "llm", label: "去配置 LLM" }],
      retryable: true,
    };
  }
  if (/频繁|限流|412|509|风控|-509/.test(lowered)) {
    const actions = [{ id: "retry", label: "稍后重试" }];
    if (actionName === "refresh_all" || actionName === "refresh_source") {
      actions.push({ id: "sources", label: "去数据源页" });
    }
    return {
      kind: "rate",
      severity: "error",
      title: "请求过于频繁",
      message: displayMessage,
      hint: "建议等待几分钟后重试，或改用单个数据源更新。",
      actions,
      retryable: true,
    };
  }
  if (/timeout|ssl|handshake|无法连接|网络|dns|代理|请求超时/.test(lowered)) {
    return {
      kind: "network",
      severity: "error",
      title: "网络异常",
      message: displayMessage,
      hint: "请检查本机网络、代理或 DNS，然后重试。",
      actions: [{ id: "retry", label: "重试" }],
      retryable: true,
    };
  }
  if (/已有任务|正在运行|仍在运行|撞车/.test(text)) {
    return {
      kind: "busy",
      severity: "error",
      title: "任务冲突",
      message: displayMessage,
      hint: "请等待当前任务结束后再试。",
      actions: [],
      retryable: false,
    };
  }
  if (/未找到活动|活动 id 无效|缺少 dynamic/.test(lowered)) {
    return {
      kind: "not_found",
      severity: "error",
      title: "活动不可用",
      message: displayMessage,
      hint: "列表可能已过期，刷新活动后再试。",
      actions: [{ id: "refresh_activities", label: "刷新列表" }],
      retryable: false,
    };
  }
  return {
    kind: "generic",
    severity: "error",
    title: "执行失败",
    message: displayMessage,
    hint: "若持续失败，可查看右下角任务日志了解详情。",
    actions: [{ id: "retry", label: "重试" }],
    retryable: true,
  };
}

export function classifyJobFailure(job) {
  return classifyFailureText(job?.message, job?.action, job?.log);
}

export function notifyJobStartError(error, action, params = {}) {
  const message = sanitizeUserText(error?.message || error);
  const code = String(error?.code || "");
  if (code === "AUTH_REQUIRED" || message.includes("请先扫码登录")) {
    showToast("请先扫码登录", "info", "完成登录与 LLM 配置后才能使用项目功能");
    return;
  }
  if (
    code === "LLM_NOT_READY" ||
    message.includes("连接测试") ||
    message.includes("配置并通过连接测试") ||
    /未配置\s*LLM|配置 LLM/i.test(message)
  ) {
    showToast("请先测试 LLM 连接", "info", "保存配置后点击「测试连接」，通过后才能使用项目功能");
    return;
  }
  const failure = classifyFailureText(error?.message || error, action);
  if (failure.severity === "info") {
    showToast(failure.message, "info", failure.hint);
  } else {
    showFailureToast(failure, { action, params });
  }
}

export async function executeFailureAction(actionId) {
  switch (actionId) {
    case "login":
      sidebarLoginBtn?.click();
      break;
    case "llm":
      scrollToLlmSettings({ focusTest: !isLlmConfigured() });
      break;
    case "retry":
      if (state.lastJobAttempt?.action) {
        try {
          await startJob(state.lastJobAttempt.action, { ...(state.lastJobAttempt.params || {}) });
        } catch (error) {
          notifyJobStartError(error, state.lastJobAttempt.action, state.lastJobAttempt.params || {});
        }
      }
      break;
    case "sources":
      switchSection("sources");
      break;
    case "refresh_activities":
      await loadActivities();
      break;
    default:
      break;
  }
}

export function renderFailureActions(container, failure, job) {
  if (!container) return;
  const actions = failure?.actions || [];
  if (!actions.length) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  container.hidden = false;
  container.innerHTML = actions
    .map(
      (action) =>
        `<button type="button" class="btn btn-secondary btn-compact btn-pill" data-failure-action="${escapeHtml(action.id)}">${escapeHtml(action.label)}</button>`
    )
    .join("");
  container.querySelectorAll("[data-failure-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (job?.action) {
        state.lastJobAttempt = {
          action: job.action,
          params: { ...(state.lastJobAttempt?.params || {}) },
        };
      }
      executeFailureAction(button.dataset.failureAction);
    });
  });
}

export function showFailureToast(failure, job) {
  if (!failure || failure.severity === "info") {
    showToast(failure?.message || "提示", "info", failure?.hint || "");
    return;
  }
  if (job?.action && failure.retryable !== false) {
    state.lastJobAttempt = {
      action: job.action,
      params: { ...(state.lastJobAttempt?.params || {}) },
    };
  }
  const actions = (failure.actions || []).map((action) => ({
    label: action.label,
    onClick: () => executeFailureAction(action.id),
  }));
  showToast(failure.message, "error", failure.hint || formatToastDetail(job), actions);
}

export function getQrcodeFocusable() {
  const panel = qrcodeModal?.querySelector(".qrcode-panel");
  if (!panel) return [];
  return [...panel.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter((el) => !el.hidden && el.getAttribute("aria-hidden") !== "true");
}

export function trapQrcodeFocus(event) {
  if (!qrcodeModal || qrcodeModal.hidden || event.key !== "Tab") return;
  const items = getQrcodeFocusable();
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

export function ensureQrcodeModalVisible() {
  if (!qrcodeModal || state.qrcodeDismissed) return;
  qrcodeLastFocus = document.activeElement;
  qrcodeModal.hidden = false;
  document.body.classList.add("modal-open");
  window.requestAnimationFrame(() => qrcodeClose?.focus());
}

export function loadQrcodeImage(refreshedAt) {
  if (!qrcodeImg || !refreshedAt) return;
  const url = `/api/login/qrcode?t=${refreshedAt}`;
  qrcodeImg.onerror = () => {
    window.setTimeout(() => {
      if (!qrcodeImg.src.includes(`t=${refreshedAt}`)) return;
      qrcodeImg.src = `${url}&retry=1`;
    }, 400);
  };
  qrcodeImg.src = url;
}

export function openQrcodeModalFresh() {
  ensureQrcodeModalVisible();
  if (qrcodeImg) qrcodeImg.removeAttribute("src");
  renderQrcodeLoginState({ result: { login_phase: "waiting" }, message: "正在生成登录二维码…" });
}

export function resolveLoginPhase(job) {
  const fromResult = job?.result?.login_phase;
  if (fromResult) return String(fromResult);
  const msg = String(job?.message || "");
  if (msg.includes("登录成功")) return "success";
  if (msg.includes("正在完成登录") || msg.includes("正在写入") || msg.includes("已确认")) return "confirming";
  if (msg.includes("请在手机上") || msg.includes("扫码成功")) return "scanned";
  if (msg.includes("二维码已过期") || msg.includes("二维码已刷新")) return "refreshing";
  if (msg.includes("扫码登录超时") || msg.includes("登录失败") || msg.includes("重新扫码")) return "error";
  return "waiting";
}

export function renderQrcodeLoginState(job) {
  const phase = resolveLoginPhase(job);
  const message = sanitizeUserText(job?.message) || "等待扫码…";
  const titles = {
    waiting: "使用哔哩哔哩 App 扫码",
    scanned: "请在手机上确认登录",
    confirming: "正在登录…",
    refreshing: "二维码已刷新",
    success: "登录成功",
    error: "登录失败",
  };
  if (qrcodeTitle) qrcodeTitle.textContent = titles[phase] || titles.waiting;
  if (qrcodeModal) qrcodeModal.dataset.phase = phase;
  if (qrcodeFrame) qrcodeFrame.dataset.phase = phase;
  if (qrcodeStatus) {
    qrcodeStatus.textContent = message;
    qrcodeStatus.classList.toggle("is-success", phase === "success");
    qrcodeStatus.classList.toggle("is-pending", phase === "scanned" || phase === "confirming");
    qrcodeStatus.classList.toggle("is-error", phase === "error");
  }
  const showOverlay = phase === "scanned" || phase === "confirming" || phase === "success" || phase === "error";
  if (qrcodeOverlay) qrcodeOverlay.hidden = !showOverlay;
  if (qrcodeOverlayText) {
    const overlayText = {
      scanned: "等待手机确认",
      confirming: "正在写入登录信息",
      success: "即将进入控制台",
      error: "请关闭后重新扫码",
    };
    qrcodeOverlayText.textContent = overlayText[phase] || "";
  }
  if (qrcodeOverlayIcon) {
    if (phase === "confirming") {
      qrcodeOverlayIcon.textContent = "";
    } else if (phase === "error") {
      qrcodeOverlayIcon.textContent = "!";
    } else {
      qrcodeOverlayIcon.textContent = "✓";
    }
  }
}

export function hideQrcodeModal(manual = false) {
  if (!qrcodeModal) return;
  if (manual) {
    state.qrcodeDismissed = true;
    cancelLoginJob();
  }
  qrcodeModal.hidden = true;
  document.body.classList.remove("modal-open");
  if (qrcodeLastFocus && typeof qrcodeLastFocus.focus === "function") {
    qrcodeLastFocus.focus();
  }
  qrcodeLastFocus = null;
}

export async function cancelLoginJob() {
  try {
    const job = await fetchJSON("/api/jobs/current");
    if (job.state === "running" && job.action === "login") {
      await fetchJSON("/api/jobs/cancel", { method: "POST" });
      stopJobPolling();
      setButtonsDisabled(false);
      updateJobUI({ state: "idle", message: "已取消扫码登录", log: "登录流程已结束" });
      showToast("已取消扫码登录", "info");
    }
  } catch (error) {
    showToast(sanitizeUserText(error.message || error), "error");
  }
}

export function syncLogDockTone(job) {
  if (!logDock) return;
  const jobState = job?.state || "idle";
  let tone = "idle";
  if (jobState === "running") tone = "running";
  else if (jobState === "success") tone = "success";
  else if (jobState === "error") tone = "error";

  logDock.dataset.tone = tone;
  logDock.classList.toggle("is-idle", tone === "idle");
  logDock.classList.toggle("is-running", tone === "running");
  logDock.classList.toggle("is-success", tone === "success");
  logDock.classList.toggle("is-error", tone === "error");

  const statusEl = document.getElementById("log-dock-status");
  if (statusEl) {
    const labels = { idle: "空闲", running: "运行中", success: "已完成", error: "失败" };
    statusEl.textContent = labels[tone] || "空闲";
    statusEl.className = `log-dock-status is-${tone}`;
  }
  if (logDockBadge) {
    logDockBadge.hidden = tone !== "running";
    logDockBadge.textContent = "运行中";
  }
}

export function scrollJobLogToBottom({ showHint = false } = {}) {
  const box = document.getElementById("job-log");
  const hint = document.getElementById("log-dock-pin-hint");
  const body = document.getElementById("log-dock-body");
  if (!box) return;
  box.scrollTop = box.scrollHeight;
  body?.classList.toggle("is-pinned", Boolean(showHint));
  if (hint) {
    hint.hidden = !showHint;
    if (showHint && !prefersReducedMotion()) {
      hint.classList.remove("is-hint-pop");
      void hint.offsetWidth;
      hint.classList.add("is-hint-pop");
    }
  }
}

export function setLogDockOpen(open) {
  state.logDockOpen = open;
  if (!logDockPanel || !logDockToggle) return;
  logDockPanel.classList.toggle("is-open", open);
  logDockPanel.setAttribute("aria-hidden", String(!open));
  logDockToggle.hidden = open;
  logDockToggle.setAttribute("aria-expanded", String(open));
  logDock?.classList.toggle("open", open);
  if (open) {
    if (!prefersReducedMotion()) {
      logDockPanel.classList.remove("is-entering");
      void logDockPanel.offsetWidth;
      logDockPanel.classList.add("is-entering");
    }
    scrollJobLogToBottom({ showHint: logDock?.classList.contains("is-running") });
  } else {
    logDockPanel.classList.remove("is-entering");
    document.getElementById("log-dock-body")?.classList.remove("is-pinned");
    const hint = document.getElementById("log-dock-pin-hint");
    if (hint) hint.hidden = true;
  }
}

export function toggleLogDock(forceOpen) {
  const next = typeof forceOpen === "boolean" ? forceOpen : !state.logDockOpen;
  setLogDockOpen(next);
}

export function participateStepLabelsForType(lotteryType) {
  return lotteryType === "预约抽奖" ? [...RESERVE_STEP_LABELS] : [...PARTICIPATE_STEP_LABELS];
}

export function participateProgressLabels(total) {
  const count = Number(total) || 0;
  if (count === 1) return ["预约"];
  if (count === 2) return [...RESERVE_STEP_LABELS];
  if (count > 0 && count <= PARTICIPATE_STEP_LABELS.length) {
    return PARTICIPATE_STEP_LABELS.slice(0, count);
  }
  return [...PARTICIPATE_STEP_LABELS];
}

export function findTripleTargetForLane(lane, job) {
  const targets = job?.result?.targets || state.tripleTargets?.items || [];
  const laneKey = String(lane?.idPart || "").trim();
  if (!laneKey) return null;
  return (
    targets.find((item) => {
      const title = String(item?.activity_title || "").trim();
      const dynamicId = String(item?.dynamic_id || "").trim();
      return (
        title === laneKey ||
        dynamicId === laneKey ||
        dynamicId.endsWith(laneKey) ||
        laneKey.endsWith(dynamicId.slice(-6))
      );
    }) || null
  );
}

export function participateActiveStepIndex(status, labelCount, labels = PARTICIPATE_STEP_LABELS) {
  const text = String(status || "");
  if (PARTICIPATE_DONE_KEYWORDS.some((keyword) => text.includes(keyword))) {
    return labelCount;
  }
  const match = text.match(/（\s*(\d+)\s*\/\s*(\d+)\s*）/);
  if (match) {
    const step = Number(match[1]);
    if (step > 0) return Math.min(step - 1, Math.max(0, labelCount - 1));
  }
  if (PARTICIPATE_PENDING_KEYWORDS.some((keyword) => text.includes(keyword)) || text.includes("检查")) {
    return -1;
  }
  for (let index = 0; index < labels.length; index += 1) {
    if (text.includes(labels[index])) return Math.min(index, labelCount - 1);
  }
  return -1;
}

export function buildPipelineStepsHtml(labels, activeIndex, options = {}) {
  const failed = Boolean(options.failed);
  return labels
    .map((label, index) => {
      let stepState = "pending";
      if (failed && activeIndex >= 0) {
        if (index < activeIndex) stepState = "done";
        else if (index === activeIndex) stepState = "failed";
      } else if (activeIndex >= labels.length) {
        stepState = "done";
      } else if (activeIndex >= 0) {
        if (index < activeIndex) stepState = "done";
        else if (index === activeIndex) stepState = "active";
      }
      const connectorDone = stepState === "done" || (activeIndex >= 0 && index < activeIndex);
      const connector =
        index < labels.length - 1
          ? `<span class="pipeline-connector ${connectorDone ? "done" : ""}"></span>`
          : "";
      const dotContent = stepState === "done" ? "✓" : stepState === "failed" ? "×" : index + 1;
      return `
        <div class="pipeline-node ${stepState}">
          <span class="pipeline-dot" aria-hidden="true">${dotContent}</span>
          <span class="pipeline-label">${escapeHtml(label)}</span>
        </div>${connector}`;
    })
    .join("");
}

export function renderPipelineSteps(labels, activeIndex) {
  if (!progressSteps) return;
  progressSteps.hidden = false;
  progressSteps.classList.remove("is-triple");
  progressSteps.innerHTML = buildPipelineStepsHtml(labels, activeIndex);
}

export function buildJobKey(job) {
  return `${job?.action || ""}:${job?.started_at || ""}`;
}

export function resetJobProgressTracking(job) {
  const nextKey = buildJobKey(job);
  if (state.activeJobKey !== nextKey) {
    state.activeJobKey = nextKey;
    state.smoothJobPercent = 0;
    if (progressBanner) progressBanner.dataset.percent = "0";
  }
}

export function parseTripleProgressLanes(message) {
  return String(message || "")
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((segment) => {
      const colonIndex = segment.indexOf(":");
      const idPart = colonIndex >= 0 ? segment.slice(0, colonIndex).trim() : segment;
      const status = colonIndex >= 0 ? segment.slice(colonIndex + 1).trim() : "等待中";
      return { idPart, status: status || "等待中" };
    });
}

export function commentFailureOptional(action) {
  if (!action || action.action !== "comment" || action.ok) return false;
  const detail = String(action.detail || "");
  return COMMENT_OPTIONAL_PATTERNS.some((pattern) => pattern.test(detail));
}

export function participationSucceeded(actions, lotteryType) {
  const actionMap = new Map((actions || []).map((item) => [item?.action, item]));
  if (lotteryType === "预约抽奖") {
    return RESERVE_REQUIRED_ACTIONS.every((name) => actionMap.get(name)?.ok === true);
  }
  if (lotteryType === "互动抽奖") {
    if (!INTERACT_REQUIRED_ACTIONS.every((name) => actionMap.get(name)?.ok === true)) return false;
    const comment = actionMap.get("comment");
    if (comment && comment.ok !== true && !commentFailureOptional(comment)) return false;
    return true;
  }
  if (lotteryType === "转发抽奖") {
    return FORWARD_REQUIRED_ACTIONS.every((name) => actionMap.get(name)?.ok === true);
  }
  return (actions || []).every((item) => item?.ok !== false);
}

export function payloadJoinedSuccess(payload) {
  if (payload?.status !== "joined") return false;
  const actions = payload?.actions || [];
  if (!actions.length) return false;
  return participationSucceeded(actions, payload?.lottery_type || "");
}

export function summarizeTripleResult(result) {
  const items = result?.items || [];
  let joined = 0;
  let failed = 0;
  for (const item of items) {
    if (payloadJoinedSuccess(item)) joined += 1;
    else failed += 1;
  }
  return { joined, failed, total: items.length };
}

export function renderActionChips(actions) {
  if (!actions?.length) return "";
  return `
    <div class="participation-result-steps">
      ${actions
        .map((item) => {
          const label = ACTION_LABELS[item?.action] || item?.action || "步骤";
          let stepState = "skipped";
          let icon = "○";
          if (item?.ok === true) {
            stepState = "done";
            icon = "✓";
          } else if (item?.ok === false) {
            stepState = "failed";
            icon = "×";
          }
          return `<span class="participation-result-step ${stepState}">${icon} ${escapeHtml(label)}</span>`;
        })
        .join("")}
    </div>`;
}

export function classifyLaneStatus(status) {
  const text = String(status || "");
  if (PARTICIPATE_FAIL_KEYWORDS.some((keyword) => text.includes(keyword))) return "failed";
  if (PARTICIPATE_DONE_KEYWORDS.some((keyword) => text.includes(keyword))) return "done";
  if (PARTICIPATE_PENDING_KEYWORDS.some((keyword) => text.includes(keyword))) return "pending";
  if (PARTICIPATE_ACTIVE_KEYWORDS.some((keyword) => text.includes(keyword))) return "active";
  return "pending";
}

export function summarizeTripleProgressLanes(lanes) {
  const doneCount = lanes.filter((lane) => classifyLaneStatus(lane.status) === "done").length;
  const activeLanes = lanes.filter((lane) => classifyLaneStatus(lane.status) === "active");
  const failedCount = lanes.filter((lane) => classifyLaneStatus(lane.status) === "failed").length;
  return { doneCount, activeLanes, failedCount };
}

export function hideParticipationResult(immediate = false) {
  if (state.jobResultTimer) {
    window.clearTimeout(state.jobResultTimer);
    state.jobResultTimer = null;
  }
  if (jobResultHint) {
    jobResultHint.hidden = true;
    jobResultHint.textContent = "";
  }
  if (jobResultActions) {
    jobResultActions.hidden = true;
    jobResultActions.innerHTML = "";
  }
  if (!jobResultBanner || jobResultBanner.hidden) return;

  if (immediate) {
    jobResultBanner.hidden = true;
    jobResultBanner.classList.remove("is-visible", "is-hiding");
    return;
  }

  jobResultBanner.classList.add("is-hiding");
  jobResultBanner.classList.remove("is-visible");
  state.jobResultTimer = window.setTimeout(() => {
    jobResultBanner.hidden = true;
    jobResultBanner.classList.remove("is-hiding");
    state.jobResultTimer = null;
  }, JOB_RESULT_EXIT_MS);
}

export function scheduleParticipationResultDismiss(delayMs = JOB_RESULT_AUTO_DISMISS_MS) {
  if (state.jobResultTimer) {
    window.clearTimeout(state.jobResultTimer);
  }
  state.jobResultTimer = window.setTimeout(() => hideParticipationResult(), delayMs);
}

export function restartParticipationResultProgress() {
  if (!jobResultProgress) return;
  jobResultProgress.style.animation = "none";
  void jobResultProgress.offsetWidth;
  jobResultProgress.style.animation = "";
}

export function renderParticipationStepResults(result) {
  const actions = result?.actions || [];
  if (!actions.length) {
    const message = sanitizeUserText(result?.message || "");
    if (result?.status === "joined" && !payloadJoinedSuccess(result)) {
      return `<p class="caption">参与未完成：${escapeHtml(message || "请查看任务日志")}</p>`;
    }
    return message
      ? `<p class="caption">${escapeHtml(message)}</p>`
      : `<p class="caption">暂无步骤明细，可在任务日志中查看详情。</p>`;
  }
  return renderActionChips(actions);
}

export function renderTripleParticipationResults(result) {
  const targets = result?.targets || [];
  const items = result?.items || [];
  const itemMap = new Map(items.map((item) => [String(item?.dynamic_id || ""), item]));
  const rows = (targets.length ? targets : items).map((entry) => {
    const dynamicId = String(entry?.dynamic_id || "");
    const payload = itemMap.get(dynamicId) || entry;
    const title = payload?.activity_title || entry?.activity_title || dynamicId || "未知活动";
    const lotteryType = payload?.lottery_type || entry?.lottery_type || "";
    const actions = payload?.actions || [];
    const succeeded = payloadJoinedSuccess(payload);
    const status = String(payload?.status || "");
    let statusLabel = "未完成";
    let statusClass = "skipped";
    if (succeeded) {
      statusLabel = "成功";
      statusClass = "success";
    } else if (status === "failed" || (status === "joined" && !payloadJoinedSuccess(payload))) {
      statusLabel = "失败";
      statusClass = "failed";
    }
    const message = sanitizeUserText(payload?.message || "");
    return `
      <div class="participation-result-item">
        <div class="participation-result-item-title" title="${escapeHtml(title)}">${escapeHtml(truncateText(title, 42))}</div>
        ${lotteryType ? `<span class="participation-result-item-meta">${escapeHtml(lotteryType)}</span>` : ""}
        <span class="participation-result-status ${statusClass}">${statusLabel}</span>
        ${actions.length ? renderActionChips(actions) : message ? `<p class="caption">${escapeHtml(message)}</p>` : ""}
      </div>`;
  });
  if (!rows.length) {
    return `<p class="caption">暂无活动结果，可在任务日志中查看详情。</p>`;
  }
  return `<div class="participation-result-list">${rows.join("")}</div>`;
}

export function showParticipationResult(job) {
  if (!jobResultBanner || (job.action !== "participate" && job.action !== "participate_triple")) return;
  if (job.result?.skipped) return;
  hideParticipationResult(true);

  const result = job.result || {};
  const isTriple = job.action === "participate_triple";
  let joined = 0;
  let failed = 0;
  let total = 1;
  if (isTriple) {
    const summary = summarizeTripleResult(result);
    joined = summary.joined;
    failed = summary.failed;
    total = summary.total;
  } else {
    joined = payloadJoinedSuccess(result) ? 1 : 0;
    failed = joined ? 0 : 1;
    total = 1;
  }

  let tone = "is-error";
  let icon = "!";
  let title = "参与未完成";
  const allSucceeded =
    job.state === "success" && total > 0 && joined >= total && failed === 0;
  if (allSucceeded) {
    tone = "is-success";
    icon = "✓";
    title = isTriple ? "三连参与完成" : "参与成功";
  } else if (joined > 0) {
    tone = "is-partial";
    icon = "◐";
    title = isTriple ? "三连参与部分完成" : "参与部分完成";
  }

  jobResultBanner.className = `job-result-banner ${tone}`;
  jobResultBanner.hidden = false;
  if (jobResultIcon) jobResultIcon.textContent = icon;
  if (jobResultEyebrow) jobResultEyebrow.textContent = isTriple ? "三连参与结果" : "参与结果";
  if (jobResultTitle) jobResultTitle.textContent = title;
  if (jobResultSummary) {
    const fallback = joined > 0 ? "请查看下方各活动执行情况" : "请查看下方步骤详情";
    jobResultSummary.textContent = sanitizeUserText(job.message) || fallback;
  }
  const needsFailureHelp = job.state === "error" || (joined > 0 && failed > 0) || (joined === 0 && failed > 0);
  const failure = needsFailureHelp ? classifyJobFailure(job) : null;
  if (jobResultHint) {
    if (failure?.hint) {
      jobResultHint.hidden = false;
      jobResultHint.textContent = failure.hint;
    } else {
      jobResultHint.hidden = true;
      jobResultHint.textContent = "";
    }
  }
  if (needsFailureHelp && failure && failure.retryable !== false) {
    state.lastJobAttempt = {
      action: job.action,
      params: { ...(state.lastJobAttempt?.params || {}) },
    };
  }
  renderFailureActions(jobResultActions, failure, job);
  if (jobResultBody) {
    jobResultBody.innerHTML = isTriple
      ? renderTripleParticipationResults(result)
      : renderParticipationStepResults(result);
  }

  jobResultBanner.classList.remove("is-hiding");
  void jobResultBanner.offsetWidth;
  jobResultBanner.classList.add("is-visible");
  restartParticipationResultProgress();
  scheduleParticipationResultDismiss();
}

export function renderTripleParticipateProgress(job) {
  if (!progressSteps) return;
  progressSteps.hidden = false;
  progressSteps.classList.add("is-triple");
  const lanes = parseTripleProgressLanes(job.progress_message);
  if (!lanes.length) {
    progressSteps.innerHTML = `<p class="caption">三连参与并行进行中…</p>`;
    return;
  }
  progressSteps.innerHTML = `
    <div class="triple-progress-stack">
      ${lanes
        .map((lane, index) => {
          const target = findTripleTargetForLane(lane, job);
          const lotteryType = target?.lottery_type || "";
          const labels = participateStepLabelsForType(lotteryType);
          const laneState = classifyLaneStatus(lane.status);
          const failed = laneState === "failed";
          const activeIndex = participateActiveStepIndex(lane.status, labels.length, labels);
          const title = truncateText(target?.activity_title || lane.idPart, 36);
          return `
            <section class="triple-progress-lane is-${laneState}">
              <div class="triple-progress-lane-head">
                <span class="triple-progress-index">#${index + 1}</span>
                <div class="triple-progress-lane-copy">
                  <span class="triple-progress-title">${escapeHtml(title)}</span>
                  <span class="triple-progress-status">${escapeHtml(lane.status)}</span>
                </div>
              </div>
              <div class="progress-pipeline triple-lane-pipeline">
                ${buildPipelineStepsHtml(labels, activeIndex, { failed })}
              </div>
            </section>`;
        })
        .join("")}
    </div>`;
}

export function renderParticipateSteps(job) {
  if (!progressSteps) return;
  if (job.state === "running" && job.action === "participate_triple") {
    renderTripleParticipateProgress(job);
    return;
  }
  if (job.state !== "running" || job.action !== "participate") {
    if (job.state === "running" && isRefreshPipelineAction(job.action)) {
      renderRefreshAllPipeline(job);
      return;
    }
    if (job.state === "running" && job.action === "refresh_watch") {
      renderRefreshWatchPipeline(job);
      return;
    }
    progressSteps.hidden = true;
    progressSteps.innerHTML = "";
    progressSteps.classList.remove("is-triple");
    return;
  }
  const total = Number(job.progress_total) || PARTICIPATE_STEP_LABELS.length;
  const current = Number(job.progress_step) || 0;
  const labels = participateProgressLabels(total);
  const activeIndex = Math.max(0, Math.min(labels.length - 1, current > 0 ? current - 1 : 0));
  renderPipelineSteps(labels, activeIndex);
}

export function refreshAllDataSourceCount(job) {
  const total = Number(job.progress_total) || REFRESH_ALL_DS_COUNT + REFRESH_ALL_PIPELINE_SUBSTEPS;
  return Math.max(1, total - REFRESH_ALL_PIPELINE_SUBSTEPS);
}

export function refreshAllPipelinePhaseFromMessage(message) {
  const text = String(message || "");
  if (/跳过.*流水线|均无新专栏|无新专栏/.test(text)) return 3;
  if (/入库|落库|写入活动库/.test(text)) return 3;
  if (/详情进度|活动详情/.test(text)) return 2;
  if (/分类|新链接/.test(text)) return 1;
  return null;
}

export function refreshAllSubprogressRatio(message) {
  const match = String(message || "").match(/\((\d+)\s*\/\s*(\d+)\)/);
  if (!match) return null;
  return Number(match[1]) / Math.max(1, Number(match[2]));
}

export function refreshAllPipelinePhase(step, dsCount, message) {
  if (step > dsCount) {
    const fromMessage = refreshAllPipelinePhaseFromMessage(message);
    if (fromMessage !== null) return fromMessage;
  }
  if (step <= dsCount) return 0;
  if (step === dsCount + 1) return 1;
  if (step === dsCount + 2) return 2;
  return 3;
}

export function renderRefreshAllPipeline(job) {
  if (!progressSteps) return;
  const step = Number(job.progress_step) || 0;
  const dsCount = refreshAllDataSourceCount(job);
  const message = job.progress_message || job.message || "";
  renderPipelineSteps(REFRESH_ALL_PIPELINE, refreshAllPipelinePhase(step, dsCount, message));
}

export function renderRefreshWatchPipeline(job) {
  if (!progressSteps) return;
  progressSteps.hidden = false;
  const step = Number(job.progress_step) || 0;
  let phase = 0;
  if (step <= 1) phase = 0;
  else if (step === 2) phase = 1;
  else if (step === 3) phase = 2;
  else phase = 3;
  renderPipelineSteps(REFRESH_WATCH_PIPELINE, phase);
}

export function calcJobProgressPercent(job) {
  const total = Number(job.progress_total) || 0;
  const step = Number(job.progress_step) || 0;
  if (total <= 0) return 8;
  if (isRefreshPipelineAction(job.action)) {
    const dsCount = refreshAllDataSourceCount(job);
    const detail = String(job.progress_message || job.message || "");
    if (step >= total) return 100;
    if (/跳过.*流水线|均无新专栏|无新专栏/.test(detail)) return 100;
    if (step <= 0) return 6;
    if (step <= dsCount) return Math.round(10 + (step / dsCount) * 38);
    const phase = refreshAllPipelinePhase(step, dsCount, detail);
    const ratio = refreshAllSubprogressRatio(detail);
    if (phase === 1) {
      return ratio != null ? Math.min(68, Math.round(50 + ratio * 18)) : 52;
    }
    if (phase === 2) {
      return ratio != null ? Math.min(90, Math.round(70 + ratio * 18)) : 74;
    }
    if (phase === 3) return 100;
  }
  if (job.action === "refresh_watch") {
    if (step <= 0) return 6;
    if (step === 1) {
      const detail = String(job.progress_message || "");
      const match = detail.match(/(\d+)\s*\/\s*(\d+)/);
      if (match) {
        const ratio = Number(match[1]) / Math.max(1, Number(match[2]));
        return Math.min(42, Math.round(10 + ratio * 32));
      }
      return 18;
    }
    if (step === 2) {
      const detail = String(job.progress_message || "");
      const match = detail.match(/\((\d+)\s*\/\s*(\d+)\)/);
      if (match) {
        const ratio = Number(match[1]) / Math.max(1, Number(match[2]));
        return Math.min(68, Math.round(46 + ratio * 20));
      }
      return 50;
    }
    if (step === 3) {
      const detail = String(job.progress_message || "");
      const match = detail.match(/\((\d+)\s*\/\s*(\d+)\)/);
      if (match) {
        const ratio = Number(match[1]) / Math.max(1, Number(match[2]));
        return Math.min(90, Math.round(72 + ratio * 16));
      }
      return 76;
    }
    if (step >= 4) return 100;
  }
  if (job.action === "participate" || job.action === "participate_triple") {
    if (total <= 0) return 0;
    return Math.max(0, Math.min(100, Math.round((step / total) * 100)));
  }
  return Math.max(0, Math.min(100, Math.round((step / total) * 100)));
}

export function setButtonsDisabled(disabled) {
  document.querySelectorAll("[data-action], [data-activity-delete]").forEach((button) => {
    button.disabled = disabled;
  });
}

export function setProgressAria(percent, labelText) {
  if (!progressTrack) return;
  const rounded = Math.max(0, Math.min(100, Math.round(percent)));
  progressTrack.setAttribute("aria-valuenow", String(rounded));
  if (labelText) {
    progressTrack.setAttribute("aria-valuetext", labelText);
  }
}

export function updateProgressUI(job) {
  const running = job.state === "running";
  document.body.classList.toggle("job-running", running);
  progressBanner.hidden = !running;
  if (!running) {
    progressFill.style.width = "0%";
    if (progressFillGlow) progressFillGlow.style.width = "0%";
    const shine = document.getElementById("progress-fill-shine");
    if (shine) shine.style.left = "0%";
    if (progressPercent) progressPercent.textContent = "0";
    if (progressPercentSuffix) {
      progressPercentSuffix.textContent = "%";
      progressPercentSuffix.hidden = false;
    }
    if (progressRing) progressRing.style.strokeDashoffset = "97.4";
    state.smoothJobPercent = 0;
    state.activeJobKey = "";
    if (progressBanner) progressBanner.dataset.percent = "0";
    setProgressAria(0, "0%");
    renderParticipateSteps(job);
    return;
  }

  resetJobProgressTracking(job);
  const display = formatJobProgressDisplay(job);
  const percent = Math.max(state.smoothJobPercent, display.percent);
  state.smoothJobPercent = percent;
  const prev = Number(progressBanner.dataset.percent || "0");
  progressBanner.dataset.percent = String(percent);
  if (percent > prev) progressBanner.classList.add("progress-tick");
  else progressBanner.classList.remove("progress-tick");
  window.setTimeout(() => progressBanner.classList.remove("progress-tick"), 420);
  progressFill.style.width = `${percent}%`;
  if (progressFillGlow) progressFillGlow.style.width = `${percent}%`;
  const shine = document.getElementById("progress-fill-shine");
  if (shine) shine.style.left = `${Math.max(0, percent - 6)}%`;
  if (progressPercent) progressPercent.textContent = display.value;
  if (progressPercentSuffix) {
    progressPercentSuffix.textContent = display.suffix;
    progressPercentSuffix.hidden = !display.showPercentSuffix && !display.suffix;
  }
  if (progressRing) {
    const circumference = 97.4;
    progressRing.style.strokeDashoffset = String(circumference - (circumference * percent) / 100);
  }
  setProgressAria(percent, `${display.showPercentSuffix ? `${Math.round(percent)}%` : display.value}${display.suffix || ""}`.trim());
  if (progressChip) {
    const chipMap = {
      participate: "参与任务",
      participate_triple: "三连参与",
      refresh_all: "同步任务",
      refresh_source: "数据源更新",
      refresh_watch: "监控扫描",
      login: "登录任务",
    };
    progressChip.textContent = chipMap[job.action] || "任务进行中";
  }
  progressLabel.textContent = formatProgressTitle(job);
  if (progressDetail) {
    progressDetail.textContent = formatProgressDetail(job);
    progressDetail.hidden = job.action === "participate";
  }
  renderParticipateSteps(job);
}

export function updateJobUI(job) {
  jobMessage.textContent = sanitizeUserText(job.message) || "暂无任务";
  jobLog.textContent = sanitizeUserText(job.log) || "";
  syncLogDockTone(job);
  if (job.state === "running") {
    toggleLogDock(true);
    scrollJobLogToBottom({ showHint: true });
  } else if (state.logDockOpen) {
    scrollJobLogToBottom({ showHint: false });
  }
  setButtonsDisabled(job.state === "running");
  updateProgressUI(job);
}

export async function startJob(action, params = {}) {
  if (!requireSetup(action)) return;
  state.lastJobAttempt = { action, params: { ...params } };
  if (action === "login") {
    try {
      const current = await fetchJSON("/api/jobs/current");
      if (current.state === "running" && current.action === "login") {
        state.qrcodeDismissed = false;
        ensureQrcodeModalVisible();
        const refreshedAt = Number(current.result?.qrcode_refreshed_at) || 0;
        if (refreshedAt && refreshedAt !== state.lastQrcodeRefresh) {
          state.lastQrcodeRefresh = refreshedAt;
          loadQrcodeImage(refreshedAt);
        }
        renderQrcodeLoginState(current);
        startRealtime();
        startPolling();
        return;
      }
    } catch {
      /* 继续发起新任务 */
    }
  }
  if (action === "participate" || action === "participate_triple") {
    hideParticipationResult(true);
    state.smoothJobPercent = 0;
    state.activeJobKey = "";
  }
  toggleLogDock(true);
  // 错误提示由调用方 notifyJobStartError 统一处理，避免重复 toast
  await fetchJSON("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, params }),
  });
  if (action === "login") {
    state.qrcodeDismissed = false;
    state.lastQrcodeRefresh = 0;
    openQrcodeModalFresh();
  }
  const current = await fetchJSON("/api/jobs/current");
  state.currentJob = current;
  updateJobUI(current);
  startRealtime();
  startPolling();
}

export function collectFinishedDynamicIds(job) {
  if (job.action === "participate_triple") {
    return (job.result?.items || []).map((item) => item?.dynamic_id).filter(Boolean);
  }
  if (job.action === "participate" && job.result?.dynamic_id) {
    return [job.result.dynamic_id];
  }
  return [];
}

export async function handleJobCompletion(job) {
  dismissRunningToasts();

  const isParticipation = job.action === "participate" || job.action === "participate_triple";
  if (job.action === "login" && job.state === "success" && !state.qrcodeDismissed) {
    renderQrcodeLoginState({
      ...job,
      result: { ...(job.result || {}), login_phase: "success" },
      message: "登录成功，账号已就绪",
    });
    await new Promise((resolve) => window.setTimeout(resolve, 450));
  }

  if (isParticipation && (job.state === "success" || job.state === "error")) {
    if (job.result?.skipped) {
      if (!job.result?.from_auto) {
        showToast(sanitizeUserText(job.message) || "当前没有可参与活动，已跳过", "info");
      }
    } else {
      showParticipationResult(job);
    }
  } else if (job.state === "success") {
    if (SYNC_TOAST_ACTIONS.has(job.action)) {
      const detail = formatToastDetail(job);
      showToast(sanitizeUserText(job.message) || "任务完成", "success", detail);
    }
  } else if (job.state === "cancelled") {
    showToast(sanitizeUserText(job.message) || "任务已取消", "info");
  } else if (job.state === "error") {
    if (job.action === "login" && !state.qrcodeDismissed) {
      renderQrcodeLoginState({
        ...job,
        result: { ...(job.result || {}), login_phase: "error" },
        message: sanitizeUserText(job.message) || "登录失败，请重试",
      });
    } else {
      const failure = classifyJobFailure(job);
      if (failure.severity === "info") {
        showToast(failure.message, "info", failure.hint || formatToastDetail(job));
      } else {
        showFailureToast(failure, job);
      }
    }
  }

  const finishedDynamicIds = collectFinishedDynamicIds(job);
  try {
    await loadSummary();
    await syncProjectState();
    await loadActivities();
    if (job.action === "refresh_watch") {
      await loadWatchUsers();
      if (job.state === "success") pulseWatchSyncCard();
    }
    if (job.action === "refresh_source" && job.state === "success") {
      const sourceId = state.lastJobAttempt?.params?.source_id;
      flashSourceRow(sourceId);
    }
  } catch (error) {
    showToast(String(error.message || error), "error");
  }
  clearActionButtonLoading();
  if (job.action === "participate_triple") {
    renderTripleParticipateBar(state.tripleTargets);
  }
  flashActivityRows(finishedDynamicIds);
  if (job.action === "login" && job.state === "success") hideQrcodeModal(false);
}

export function bindActionButtons() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      const params = {};
      if (button.dataset.dynamicId) params.dynamic_id = button.dataset.dynamicId;
      if (button.dataset.sourceId) params.source_id = button.dataset.sourceId;
      if (action === "participate_triple") {
        Object.assign(params, buildActivityFilterJobParams());
      }
      if (action === "participate") {
        setButtonLoading(button, true, { label: "参与中…" });
      }
      if (action === "participate_triple") {
        setButtonLoading(button, true, { label: "参与中" });
      }
      if (action === "refresh_source") {
        setButtonLoading(button, true, { label: "更新中…" });
        setSourceRowUpdating(params.source_id, true);
      }
      try {
        if (action === "refresh_all") {
          const confirmed = await confirmRefreshAll();
          if (!confirmed) {
            setButtonLoading(button, false);
            return;
          }
        }
        await startJob(action, params);
      } catch (error) {
        notifyJobStartError(error, action, params);
        setButtonLoading(button, false);
        if (action === "refresh_source") {
          setSourceRowUpdating(params.source_id, false);
        }
        if (action === "participate_triple") {
          renderTripleParticipateBar(state.tripleTargets);
        }
      }
    });
  });
}

export function resolveJobPollIntervalMs(action) {
  if (action === "login") return 500;
  if (action === "participate" || action === "participate_triple") return 400;
  return 1000;
}

export function stopJobPolling() {
  if (state.polling) {
    window.clearTimeout(state.polling);
    state.polling = null;
  }
}

export function applyRunningJobView(job) {
  state.currentJob = job;
  updateJobUI(job);
  if (job.state === "running" && job.action === "login" && !state.qrcodeDismissed) {
    ensureQrcodeModalVisible();
    renderQrcodeLoginState(job);
    const refreshedAt = Number(job.result?.qrcode_refreshed_at) || 0;
    if (refreshedAt && refreshedAt !== state.lastQrcodeRefresh) {
      state.lastQrcodeRefresh = refreshedAt;
      loadQrcodeImage(refreshedAt);
    }
  }
}

export async function finishJobOnce(job) {
  const key = `${job.id || ""}:${job.action || ""}:${job.state || ""}:${job.finished_at || ""}`;
  if (key && key === state.lastFinishedJobKey) return;
  state.lastFinishedJobKey = key;
  state.currentJob = job;
  updateJobUI(job);

  if (job.action === "login" && (job.state === "cancelled" || job.state === "idle")) {
    stopJobPolling();
    setButtonsDisabled(false);
    hideQrcodeModal(false);
    if (job.state === "cancelled") {
      showToast(sanitizeUserText(job.message) || "已取消扫码登录", "info");
    }
    return;
  }
  stopJobPolling();
  try {
    await handleJobCompletion(job);
  } catch (error) {
    console.error("finishJobOnce failed", error);
  }
}

export function mergeJobProgress(payload) {
  const base = state.currentJob || {};
  return {
    ...base,
    id: payload.id ?? base.id,
    state: "running",
    action: base.action || "",
    label: base.label || "",
    source: base.source || "ui",
    progress_step: payload.step ?? base.progress_step ?? 0,
    progress_total: payload.total ?? base.progress_total ?? 0,
    message: payload.message || base.message || "",
    progress_message: payload.message || base.progress_message || "",
    log: base.log || "",
    result: { ...(base.result || {}), ...(payload.result || {}) },
  };
}

export function appendJobLogChunk(chunk) {
  const base = state.currentJob || { state: "running", log: "" };
  const current = String(base.log || "").trim();
  const next = current ? `${current}\n${chunk}` : chunk;
  state.currentJob = { ...base, log: next, state: base.state || "running" };
  updateJobUI(state.currentJob);
}

export function startPolling() {
  // H2：SSE 健康时不双通道
  if (state.sseHealthy && state.eventSource) return;
  if (state.polling) return;
  const poll = async () => {
    if (state.sseHealthy && state.eventSource) {
      stopJobPolling();
      return;
    }
    try {
      const job = await fetchJSON("/api/jobs/current");
      state.currentJob = job;
      updateJobUI(job);
      if (job.state === "running") {
        if (job.action === "login" && !state.qrcodeDismissed) {
          ensureQrcodeModalVisible();
          renderQrcodeLoginState(job);
          const refreshedAt = Number(job.result?.qrcode_refreshed_at) || 0;
          if (refreshedAt && refreshedAt !== state.lastQrcodeRefresh) {
            state.lastQrcodeRefresh = refreshedAt;
            loadQrcodeImage(refreshedAt);
          }
        }
        state.polling = window.setTimeout(poll, resolveJobPollIntervalMs(job.action));
        return;
      }
      stopJobPolling();
      await finishJobOnce(job);
    } catch (error) {
      console.error(error);
      state.polling = window.setTimeout(poll, 1500);
    }
  };
  poll();
}
