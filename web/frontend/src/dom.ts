// @ts-nocheck
/* eslint-disable */
/** Migrated from web/static/app.js — logic preserved. */


export const jobMessage = document.getElementById("job-message");

export const jobLog = document.getElementById("job-log");

export const statsGrid = document.getElementById("stats-grid");

export const sourceGrid = document.getElementById("source-grid");

export const watchUserGrid = document.getElementById("watch-user-grid");

export const watchUsersBadge = document.getElementById("watch-users-badge");

export const watchMetricCount = document.getElementById("watch-metric-count");

export const watchMetricLinks = document.getElementById("watch-metric-links");

export const watchLastSynced = document.getElementById("watch-last-synced");

export const watchNextWindow = document.getElementById("watch-next-window");

export const watchWindowCap = document.getElementById("watch-window-cap");

export const watchAddForm = document.getElementById("watch-add-form");

export const watchAddMidInput = document.getElementById("watch-add-mid");

export const watchAddMidError = document.getElementById("watch-add-mid-error");

export const watchAddBtn = document.getElementById("watch-add-btn");

export const accountHero = document.getElementById("account-hero");

export const sidebarAccountCard = document.getElementById("sidebar-account-card");

export const sidebarLoginBtn = document.getElementById("sidebar-login");

export const sidebarLogoutBtn = document.getElementById("sidebar-logout");

export const appConfirmModal = document.getElementById("app-confirm-modal");

export const appConfirmBackdrop = document.getElementById("app-confirm-backdrop");

export const appConfirmEyebrow = document.getElementById("app-confirm-eyebrow");

export const appConfirmTitle = document.getElementById("app-confirm-title");

export const appConfirmDesc = document.getElementById("app-confirm-desc");

export const appConfirmBullets = document.getElementById("app-confirm-bullets");

export const appConfirmCancel = document.getElementById("app-confirm-cancel");

export const appConfirmYes = document.getElementById("app-confirm-yes");

export const appConfirmSecondary = document.getElementById("app-confirm-secondary");

export const onboardingPanel = document.getElementById("onboarding-panel");

export const onboardingStepsEl = document.getElementById("onboarding-steps");

export const onboardingProgressFill = document.getElementById("onboarding-progress-fill");

export const onboardingProgressLabel = document.getElementById("onboarding-progress-label");

export const onboardingFootNote = document.getElementById("onboarding-foot-note");

export const onboardingPrimaryBtn = document.getElementById("onboarding-primary");

export const onboardingSkipBtn = document.getElementById("onboarding-skip");

export const sidebarRefreshBtn = document.getElementById("sidebar-refresh-account");

export const activitiesBody = document.getElementById("activities-body");

export const activitiesCards = document.getElementById("activities-cards");

export const filterResultSummary = document.getElementById("filter-result-summary");

export const participateTextFeedback = document.getElementById("participate-text-feedback");

export const llmActionFeedback = document.getElementById("llm-action-feedback");

export const filterDrawWindowHint = document.getElementById("filter-draw-window-hint");

export const pagination = document.getElementById("pagination");

export const deletedActivitiesToggle = document.getElementById("deleted-activities-toggle");

export const deletedActivitiesCount = document.getElementById("deleted-activities-count");

export const deletedActivitiesSection = document.getElementById("deleted-activities-section");

export const deletedActivitiesList = document.getElementById("deleted-activities-list");

export const deletedActivitiesClose = document.getElementById("deleted-activities-close");

export const qrcodeModal = document.getElementById("qrcode-modal");

export const qrcodeImg = document.getElementById("qrcode-img");

export const qrcodeTitle = document.getElementById("qrcode-title");

export const qrcodeFrame = document.getElementById("qrcode-frame");

export const qrcodeOverlay = document.getElementById("qrcode-overlay");

export const qrcodeOverlayIcon = document.getElementById("qrcode-overlay-icon");

export const qrcodeOverlayText = document.getElementById("qrcode-overlay-text");

export const qrcodeClose = document.getElementById("qrcode-close");

export const qrcodeStatus = document.getElementById("qrcode-status");

export const progressBanner = document.getElementById("progress-banner");

export const progressLabel = document.getElementById("progress-label");

export const progressDetail = document.getElementById("progress-detail");

export const progressFill = document.getElementById("progress-fill");

export const progressFillGlow = document.getElementById("progress-fill-glow");

export const progressPercent = document.getElementById("progress-percent");

export const progressPercentSuffix = document.querySelector(".progress-percent-suffix");

export const progressRing = document.getElementById("progress-ring");

export const progressTrack = document.getElementById("progress-track");

export const progressChip = document.getElementById("progress-chip");

export const progressSteps = document.getElementById("progress-steps");

export const jobResultBanner = document.getElementById("job-result-banner");

export const jobResultIcon = document.getElementById("job-result-icon");

export const jobResultEyebrow = document.getElementById("job-result-eyebrow");

export const jobResultTitle = document.getElementById("job-result-title");

export const jobResultSummary = document.getElementById("job-result-summary");

export const jobResultHint = document.getElementById("job-result-hint");

export const jobResultActions = document.getElementById("job-result-actions");

export const jobResultBody = document.getElementById("job-result-body");

export const jobResultProgress = document.getElementById("job-result-progress");

export const jobResultClose = document.getElementById("job-result-close");

export const toastStack = document.getElementById("toast-stack");

export const JOB_RESULT_AUTO_DISMISS_MS = 3000;

export const JOB_RESULT_EXIT_MS = 340;

export const JOB_RESULT_HOVER_DISMISS_MS = 2200;

export const INLINE_FEEDBACK_MS = 5000;

export const ONBOARDING_STORAGE_KEY = "binggo-onboarding-v1";

export const ONBOARDING_STEPS = [
  {
    id: "login",
    title: "扫码登录",
    desc: "使用哔哩哔哩 App 扫码，登录后才能参与抽奖与保存配置。",
    cta: "去登录",
  },
  {
    id: "llm_save",
    title: "保存 LLM 配置",
    desc: "填写 API Key 与模型名称并保存。转发抽奖解析依赖 LLM，为项目启动的必要条件。",
    cta: "去配置",
  },
  {
    id: "llm_test",
    title: "测试 LLM 连接",
    desc: "保存后点击「测试连接」，通过后才能使用参与、刷新等功能。",
    cta: "去测试",
  },
  {
    id: "try",
    title: "去活动页试一次",
    desc: "进入活动列表，尝试参与单个活动或使用「三连参与」。",
    cta: "去活动页",
  },
];

export const SYNC_TOAST_ACTIONS = new Set(["refresh_all", "refresh_source", "refresh_watch", "refresh_status"]);

export const inlineFeedbackTimers = new Map();

export const logDock = document.getElementById("log-dock");

export const logDockPanel = document.getElementById("log-dock-panel");

export const logDockToggle = document.getElementById("log-dock-toggle");

export const logDockBadge = document.getElementById("log-dock-badge");

export const autoDock = document.getElementById("auto-dock");

export const autoDockPanel = document.getElementById("auto-dock-panel");

export const autoDockToggle = document.getElementById("auto-dock-toggle");

export const autoDockBadge = document.getElementById("auto-dock-badge");

export const autoDockStatus = document.getElementById("auto-dock-status");

export const autoDockCountdown = document.getElementById("auto-dock-countdown");

export const autoDockJob = document.getElementById("auto-dock-job");

export const autoDockScheduler = document.getElementById("auto-dock-scheduler");

export const autoDockPhase = document.getElementById("auto-dock-phase");

export const autoDockHint = document.getElementById("auto-dock-hint");

export const autoDockPipeline = document.getElementById("auto-dock-pipeline");

export const autoDockToggleMeta = document.getElementById("auto-dock-toggle-meta");

export const autoDockFatal = document.getElementById("auto-dock-fatal");

export const autoDockFatalText = document.getElementById("auto-dock-fatal-text");

export const autoDockStartBtn = document.getElementById("auto-dock-start");

export const autoDockStopBtn = document.getElementById("auto-dock-stop");

export const PARTICIPATE_STEP_LABELS = ["点赞", "关注", "收藏", "转发", "评论"];

export const PARTICIPATE_ACTIVE_KEYWORDS = ["点赞", "关注", "收藏", "转发", "评论", "预约", "正在", "准备", "检查"];

export const PARTICIPATE_DONE_KEYWORDS = ["完成", "成功", "已参与", "参与成功", "joined"];

export const PARTICIPATE_FAIL_KEYWORDS = ["失败", "未完成", "错误", "failed", "已停止", "已取消"];

export const PARTICIPATE_PENDING_KEYWORDS = ["排队", "等待"];

export const REFRESH_ALL_PIPELINE = ["数据源", "分类", "详情", "落库"];

export const REFRESH_WATCH_PIPELINE = ["扫描", "分类", "详情", "落库"];

export const REFRESH_ALL_PIPELINE_SUBSTEPS = 3;

export const REFRESH_WATCH_PIPELINE_SUBSTEPS = 3;

export const REFRESH_ALL_DS_COUNT = 6;

export const ACTION_LABELS = {
  like: "点赞",
  follow: "关注",
  favorite: "收藏",
  repost: "转发",
  comment: "评论",
  reserve: "预约",
};

export const INTERACT_REQUIRED_ACTIONS = ["like", "follow", "favorite", "repost"];

export const FORWARD_REQUIRED_ACTIONS = ["like", "follow", "favorite", "repost", "comment"];

export const RESERVE_REQUIRED_ACTIONS = ["follow", "reserve"];

export const RESERVE_STEP_LABELS = ["关注", "预约"];

export const COMMENT_OPTIONAL_PATTERNS = [/关注UP主/i, /关注 up/i, /7\s*天/i, /code=12078/i];

export const LOGIN_REQUIRED_ACTIONS = new Set([
  "refresh_all",
  "refresh_source",
  "refresh_watch",
  "refresh_status",
  "participate",
  "participate_triple",
]);

export const LLM_REQUIRED_ACTIONS = new Set([
  "refresh_all",
  "refresh_source",
  "refresh_watch",
  "participate",
  "participate_triple",
]);
