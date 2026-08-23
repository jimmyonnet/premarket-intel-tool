export const GATEWAY_ORIGIN = "https://premarket-gw-pxz3yyqw.manus.space";

const ACTIVE_STATES = Object.freeze({
  queued: true,
  in_progress: true,
  completed: true,
  failed: true,
  already_running: true,
  not_configured: true,
});

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
  let popup = null;
  let resetTimer = null;
  const notify = (message) => {
    if (windowRef.pm && typeof windowRef.pm.showToast === "function") windowRef.pm.showToast(message);
  };
  const resetButton = () => {
    requestId = null;
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
  const onMessage = (event) => {
    if (event.origin !== gatewayOrigin || event.source !== popup) return;
    const data = event.data || {};
    if (data.source !== "premarket-update-gateway" || data.requestId !== requestId || !ACTIVE_STATES[data.state]) return;
    if (data.state === "queued") {
      button.textContent = "⏳ 已啟動更新";
      button.title = data.message || "已啟動資料更新，正在安全追蹤執行結果。";
      notify(button.title);
    } else if (data.state === "in_progress" || data.state === "already_running") {
      button.textContent = "⏳ 更新進行中";
      button.title = data.message || "已有資料更新正在執行中，請稍候。";
      notify(button.title);
    } else if (data.state === "completed") {
      finish("✓ 更新已完成", data.message || "資料更新已完成，請重新整理頁面取得最新內容。", false);
      try { popup.close(); } catch (_) {}
    } else {
      finish("⚠ 更新未完成", data.message || "資料更新未成功完成，請稍後再試。", true);
    }
  };
  const onClick = () => {
    if (button.disabled) return;
    requestId = (windowRef.crypto && windowRef.crypto.randomUUID ? windowRef.crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2)).replace(/-/g, "");
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
