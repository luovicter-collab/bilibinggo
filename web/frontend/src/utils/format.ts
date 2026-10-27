// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */

import { state } from "../state";
import { ACTION_LABELS, PARTICIPATE_STEP_LABELS } from "../dom";
import { calcJobProgressPercent, parseTripleProgressLanes, participateProgressLabels, summarizeTripleProgressLanes } from "../jobs/index";
import { escapeHtml, sanitizeUserText } from "../utils/text";

export function lotteryTypeTone(type) {
  const text = String(type || "");
  if (text.includes("互动")) return "interact";
  if (text.includes("转发")) return "repost";
  if (text.includes("预约")) return "reserve";
  return "default";
}

export function isLotterySoon(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/);
  if (!match) return false;
  const [, y, m, d, hh, mm] = match.map(Number);
  const target = new Date(y, m - 1, d, hh, mm).getTime();
  if (Number.isNaN(target)) return false;
  const now = Date.now();
  const delta = target - now;
  return delta >= 0 && delta <= 3 * 24 * 60 * 60 * 1000;
}

export function activityStatusTone(status) {
  if (status === "已参加") return "joined";
  if (status === "已结束") return "ended";
  return "pending";
}

export function formatUnixTimestamp(ts) {
  const value = Number(ts);
  if (!value) return "尚未同步";
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return "尚未同步";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatWatchWindow(start, end) {
  const fmt = (ts) => {
    const value = Number(ts);
    if (!value) return "—";
    const date = new Date(value * 1000);
    if (Number.isNaN(date.getTime())) return "—";
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };
  const from = fmt(start);
  const to = fmt(end);
  if (from === "—" || to === "—") return "—";
  return `${from} — ${to}`;
}

export function formatWindowDays(seconds) {
  const days = Math.max(1, Math.round(Number(seconds || 0) / 86400));
  return `${days} 天`;
}

export function formatToastDetail(job) {
  if (!job?.log) return "";
  const lines = sanitizeUserText(job.log)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 3);
  return lines.join(" · ");
}

export function formatLastParticipation(last) {
  if (!last) return "";
  const status = last.status || "";
  const message = last.message || "";
  if (status === "joined") return message || "参与成功";
  if (status === "failed") {
    const failed = (last.actions || []).filter((item) => item && item.ok === false);
    if (failed.length) {
      const labels = failed.map((item) => ACTION_LABELS[item.action] || item.action).join("、");
      return `失败：${labels}${message ? `（${message}）` : ""}`;
    }
    return message || "参与失败";
  }
  return message || status;
}

export function badgeClass(status) {
  if (status === "已参加") return "badge joined";
  if (status === "已结束") return "badge ended";
  return "badge pending";
}

export function formatAutoCountdown(targetUnix) {
  if (!targetUnix) return "—";
  const nowSec = Math.floor((Date.now() + state.autoServerSkewMs) / 1000);
  const diff = Math.max(0, Number(targetUnix) - nowSec);
  const hours = Math.floor(diff / 3600);
  const minutes = Math.floor((diff % 3600) / 60);
  const seconds = diff % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function formatJobProgressDisplay(job) {
  const step = Number(job.progress_step) || 0;
  const total = Number(job.progress_total) || 0;
  const percent = calcJobProgressPercent(job);
  if (job.action === "participate" || job.action === "participate_triple") {
    if (total > 0) {
      return { percent, value: `${step}/${total}`, suffix: " 步", showPercentSuffix: false };
    }
    return { percent: 0, value: "0", suffix: "", showPercentSuffix: false };
  }
  return { percent, value: String(percent), suffix: "%", showPercentSuffix: true };
}

export function formatProgressTitle(job) {
  if (job.action === "participate") return "正在参与活动";
  if (job.action === "participate_triple") {
    const lanes = parseTripleProgressLanes(job.progress_message);
    const count = lanes.length || Number(job.result?.targets?.length) || 3;
    return `三连参与 · 并行 ${count} 个活动`;
  }
  return job.label || "任务运行中…";
}

export function formatProgressDetail(job) {
  if (job.action === "participate") {
    const message = sanitizeUserText(job.progress_message || job.message || "");
    if (message && !message.includes("|")) return message;
    const step = Number(job.progress_step) || 0;
    const total = Number(job.progress_total) || PARTICIPATE_STEP_LABELS.length;
    const labels = participateProgressLabels(total);
    if (step > 0 && step <= labels.length) return `当前步骤：${labels[step - 1]}`;
    return "准备开始参与…";
  }
  if (job.action === "participate_triple") {
    const lanes = parseTripleProgressLanes(job.progress_message);
    if (!lanes.length) return "并行处理中，请稍候…";
    const { doneCount, activeLanes, failedCount } = summarizeTripleProgressLanes(lanes);
    if (failedCount > 0) {
      return `继续处理中 ${doneCount}/${lanes.length} 完成 · ${failedCount} 个失败已跳过`;
    }
    if (activeLanes.length > 1) {
      return `并行进行中 ${doneCount}/${lanes.length} · ${activeLanes.length} 个活动同时执行`;
    }
    if (activeLanes.length === 1) {
      return `并行进行中 ${doneCount}/${lanes.length} · 当前：…${activeLanes[0].idPart} ${activeLanes[0].status}`;
    }
    return `并行进行中 ${doneCount}/${lanes.length} 个活动已完成步骤`;
  }
  return sanitizeUserText(job.progress_message || job.message || "请稍候，任务在后台执行中");
}

export function formatAccountStat(value, loggedIn, loading = false) {
  if (value === null || value === undefined) {
    if (!loggedIn) return "—";
    return loading ? "…" : 0;
  }
  return value;
}

export function formatFilterSummary(payload) {
  const total = Number(payload.total) || 0;
  const page = Number(payload.page) || 1;
  const pages = Math.max(1, Number(payload.pages) || 1);
  const filters = [];
  const { q, type, status, drawWindow, sort, order } = state.filters;
  if (q) filters.push(`关键词「${escapeHtml(q)}」`);
  if (type) filters.push(escapeHtml(type));
  if (status) filters.push(escapeHtml(status));
  if (drawWindow === "soon") filters.push("即将开奖");
  if (sort === "heat") filters.push(order === "asc" ? "热度升序" : "热度降序");
  const filterText = filters.length ? `（${filters.join(" · ")}）` : "";
  if (total === 0) return `未找到匹配活动${filterText}`;
  return `共 <strong class="filter-summary-count">${total}</strong> 条${filterText} · 第 ${page}/${pages} 页`;
}

export function formatHeat(item) {
  if (item?.heat_missing) return "—";
  const value = Number(item?.repost_count) || 0;
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`;
  return String(value);
}

export function formatLotteryTime(value) {
  const text = String(value || "").trim();
  if (!text || text === "—") return "—";
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(text)) return text;
  return "—";
}
