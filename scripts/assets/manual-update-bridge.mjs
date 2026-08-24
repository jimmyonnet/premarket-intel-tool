export const GATEWAY_ORIGIN = "https://premarket-gw-pxz3yyqw.manus.space";

const WORKFLOW_RUNS_API = "https://api.github.com/repos/jimmyonnet/premarket-intel-tool/actions/workflows/build-premarket-page.yml/runs";
const ACTIVE_STATES = Object.freeze({
  queued: true,
  in_progress: true,
  completed: true,
  failed: true,
  already_running: true,
  not_configured: true,
});
const RECONCILE_ATTEMPTS = 12;
const RECONCILE_INTERVAL_MS = 5000;

function isRecentManualRun(run, startedAt) {
  if (!run || run.event !== "workflow_dispatch") return false;
  const createdAt = Date.parse(run.created_at || "");
  return Number.isFinite(createdAt) && createdAt >= startedAt - 30000;
}

export function initializeManualUpdateBridge({
  windowRef = window,
  documentRef = windowRef.document,
  gatewayOrigin = GATEWAY_ORIGIN,
  buttonId = "manual-update-button",
} = {}) {
  const button = documentRef.getElementById(buttonId);
  if (!button) return () => {};

  const originalLabel = button.textContent;
  let requestId = null;
  let requestStartedAt = 0;
  let popup = null;
  let resetTimer = null;
  const notify = (message) => {
    if (windowRef.pm && typeof windowRef.pm.showToast === "function") windowRef.pm.showToast(message);
  };
  const resetButton = () => {
    requestId = null;
    requestStartedAt = 0;
    popup = null;
    button.disabled = false;
    button.textContent = originalLabel;
    button.title = "安全啟動資料更新";
  };
  const finish = (label, message, isError) => {
    button.textContent = label;
    button.title = message;
    notify(message);
    windowRef.clearTimeout(resetTimer);
    resetTimer = windowRef.setTimeout(resetButton, isError ? 4500 : 3200);
  };
  const setProgress = (label, message) => {
    button.textContent = label;
    button.title = message;
    notify(message);
  };
  const reloadPageWithFreshData = () => {
    const nextUrl = new URL(windowRef.location.href);
    nextUrl.searchParams.set("refresh", String(Date.now()));
    windowRef.location.assign(nextUrl.toString());
  };
  const completeUpdate = (message) => {
    finish("✓ 更新已完成", message || "資料更新已完成，頁面即將重新整理取得最新內容。", false);
    try { popup.close(); } catch (_) {}
    windowRef.setTimeout(reloadPageWithFreshData, 700);
  };
  const findRecentWorkflowRun = async (startedAt) => {
    if (typeof windowRef.fetch !== "function") return null;
    const response = await windowRef.fetch(
      `${WORKFLOW_RUNS_API}?event=workflow_dispatch&branch=main&per_page=20`,
      {
        cache: "no-store",
        headers: { Accept: "application/vnd.github+json" },
      },
    );
    if (!response.ok) return null;
    const payload = await response.json();
    return (payload.workflow_runs || []).find((run) => isRecentManualRun(run, startedAt)) || null;
  };
  const reconcileGatewayFailure = async (expectedRequestId, startedAt, gatewayMessage) => {
    for (let attempt = 0; attempt < RECONCILE_ATTEMPTS; attempt += 1) {
      if (requestId !== expectedRequestId) return null;
      let run = null;
      try {
        run = await findRecentWorkflowRun(startedAt);
      } catch (_) {
        run = null;
      }
      if (run && run.status === "completed") {
        if (run.conclusion === "success") {
          return { success: true, message: "GitHub Actions 已完成資料更新，頁面即將重新整理取得最新內容。" };
        }
        return {
          success: false,
          message: `GitHub Actions 更新失敗${run.conclusion ? `（${run.conclusion}）` : ""}，請查看 workflow 記錄。`,
        };
      }
      if (run && (run.status === "queued" || run.status === "in_progress")) {
        setProgress("⏳ 更新進行中", "安全閘道回報異常，但 GitHub Actions 仍在執行，請稍候。");
      } else {
        setProgress("⏳ 等待更新結果", "正在核對 GitHub Actions 的實際更新狀態，請稍候。");
      }
      if (attempt < RECONCILE_ATTEMPTS - 1) await new Promise((resolve) => windowRef.setTimeout(resolve, RECONCILE_INTERVAL_MS));
    }
    return { success: false, message: gatewayMessage || "更新未成功完成，請稍後再試。" };
  };
  const onMessage = (event) => {
    if (event.origin !== gatewayOrigin || event.source !== popup) return;
    const data = event.data || {};
    if (data.source !== "premarket-update-gateway" || data.requestId !== requestId || !ACTIVE_STATES[data.state]) return;
    if (data.state === "queued") {
      setProgress("⏳ 已啟動更新", data.message || "已啟動資料更新，正在安全追蹤執行結果。");
    } else if (data.state === "in_progress" || data.state === "already_running") {
      setProgress("⏳ 更新進行中", data.message || "已有資料更新正在執行中，請稍候。");
    } else if (data.state === "completed") {
      completeUpdate(data.message);
    } else {
      const expectedRequestId = requestId;
      const startedAt = requestStartedAt;
      const gatewayMessage = data.message || "安全更新閘道回報更新未成功完成，正在核對 GitHub Actions 實際狀態。";
      void reconcileGatewayFailure(expectedRequestId, startedAt, gatewayMessage).then((outcome) => {
        if (!outcome || requestId !== expectedRequestId) return;
        if (outcome.success) completeUpdate(outcome.message);
        else finish("⚠ 更新未完成", outcome.message, true);
      });
    }
  };
  const onClick = () => {
    if (button.disabled) return;
    requestId = (windowRef.crypto && windowRef.crypto.randomUUID ? windowRef.crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2)).replace(/-/g, "");
    requestStartedAt = Date.now();
    const bridgeUrl = new URL("/bridge", gatewayOrigin);
    bridgeUrl.searchParams.set("origin", windowRef.location.origin);
    bridgeUrl.searchParams.set("requestId", requestId);
    button.disabled = true;
    button.textContent = "⏳ 正在安全啟動…";
    button.title = "正在驗證授權並啟動資料更新";
    popup = windowRef.open(bridgeUrl.toString(), "premarket-update-" + requestId, "popup=yes,width=480,height=560");
    if (!popup) finish("⚠ 無法開啟授權視窗", "瀏覽器封鎖了安全授權視窗，請允許彈出式視窗後再試。", true);
  };

  windowRef.addEventListener("message", onMessage);
  button.addEventListener("click", onClick);
  return () => {
    windowRef.removeEventListener("message", onMessage);
    button.removeEventListener("click", onClick);
    windowRef.clearTimeout(resetTimer);
  };
}
