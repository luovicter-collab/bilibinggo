// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "./state";
import { bindOnboardingPanel, loadAccount, loadAccountExtras, logoutAccount, requestLogoutConfirm, syncProjectState } from "./account/index";
import { bindDeletedActivityControls, bindFilterPills, loadActivities, loadSummary } from "./activities/index";
import { bindAutoDock, fetchAutoStatus, setAutoDockOpen } from "./auto/index";
import { sidebarLogoutBtn, sidebarRefreshBtn } from "./dom";
import { bindActionButtons, setLogDockOpen, startPolling } from "./jobs/index";
import { startRealtime } from "./realtime/sse";
import { bindLlmApiKeyToggle, bindParticipateSettings, bindSettingsDirtyTracking, loadSettings, refreshLlmSettings, resetParticipateText, saveLlmSettings, saveParticipateText, testLlmSettings } from "./settings/index";
import { bindNavigation } from "./shell/nav";
import { initSystemPreferences } from "./shell/theme";
import { showToast } from "./shell/toast";
import { playOverviewEnter, setButtonLoading } from "./utils/motion";
import { sanitizeUserText } from "./utils/text";
import { bindDiagnosticsExport } from "./diagnostics/index";
import { bindCheckUpdates, loadRuntimeInfo } from "./runtime/index";
import { bindWatchUsers, loadWatchUsers } from "./watch/index";

export async function init() {
  initSystemPreferences();
  setLogDockOpen(false);
  setAutoDockOpen(false);
  bindNavigation();
  bindAutoDock();
  bindFilterPills();
  bindDeletedActivityControls();
  bindParticipateSettings();
  bindSettingsDirtyTracking();
  bindLlmApiKeyToggle();
  bindWatchUsers();
  bindOnboardingPanel();
  bindActionButtons();
  bindDiagnosticsExport();
  bindCheckUpdates();
  loadRuntimeInfo().catch(() => {});
  await syncProjectState();
  try {
    const job = await loadSummary();
    if (job) state.currentJob = job;
    await fetchAutoStatus().catch(() => {});
    loadWatchUsers().catch(() => {});
    await loadActivities();
    startRealtime();
    if (job?.state === "running") startPolling();
  } catch (error) {
    showToast(sanitizeUserText(error.message || error) || "数据加载失败", "error");
  }
  playOverviewEnter();
}

document.getElementById("refresh-llm-settings")?.addEventListener("click", () => {
  refreshLlmSettings().catch(() => {});
});

document.getElementById("test-llm-settings")?.addEventListener("click", () => {
  testLlmSettings().catch(() => {});
});

document.getElementById("save-llm-settings")?.addEventListener("click", () => {
  saveLlmSettings().catch(() => {});
});

document.getElementById("save-participate-text")?.addEventListener("click", () => {
  saveParticipateText().catch(() => {});
});

document.getElementById("reset-participate-text")?.addEventListener("click", () => {
  resetParticipateText().catch(() => {});
});

sidebarRefreshBtn?.addEventListener("click", async () => {
  setButtonLoading(sidebarRefreshBtn, true, { label: "刷新中…" });
  try {
    const account = await loadAccount();
    const merged = (await loadAccountExtras()) || account;
    await loadSettings();
    if (!merged?.at_alert?.increased) {
      showToast("状态已同步", "success");
    }
  } catch (error) {
    showToast(String(error.message || error), "error");
  } finally {
    setButtonLoading(sidebarRefreshBtn, false);
  }
});

sidebarLogoutBtn?.addEventListener("click", async () => {
  const confirmed = await requestLogoutConfirm();
  if (!confirmed) return;
  sidebarLogoutBtn.disabled = true;
  try {
    await logoutAccount();
  } catch (error) {
    showToast(String(error.message || error), "error");
  } finally {
    sidebarLogoutBtn.disabled = false;
  }
});


window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  syncProjectState().catch((error) => {
    showToast(String(error.message || error), "error");
  });
});
