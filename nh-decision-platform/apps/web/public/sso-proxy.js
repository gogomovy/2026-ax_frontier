/*
 * 사내 SSO 티켓 받기 (Phase R · 가이드 §2-7 sso-proxy.html) — 서버(/backend/auth/nc/init)가 nonce 를 붙여 이 페이지로 보낸다.
 * PC 의 NC 에이전트(https://127.0.0.1:13015)에서 nonce 로 티켓을 받아 콜백으로 넘긴다. 미로그인이면 NLS 로그인 페이지로.
 * Chrome · Edge(Non-ActiveX) 경로만 — IE(ActiveX) 는 지원하지 않는다.
 */
(function () {
  "use strict";
  var params = new URLSearchParams(window.location.search);
  var NONCE = params.get("nonce") || "";
  var CALLBACK = params.get("callback") || "/backend/auth/nc/callback";
  var LOGIN_URL = params.get("loginUrl") || "";
  // 같은 출처 상대 경로만 — 다른 사이트로 티켓을 넘기지 않게
  if (CALLBACK.charAt(0) !== "/" || CALLBACK.charAt(1) === "/") CALLBACK = "/backend/auth/nc/callback";
  var CALLBACK_URL = window.location.origin + CALLBACK;
  var done = false;

  function $(id) { return document.getElementById(id); }
  function showError(text) {
    if (done) return;
    done = true;
    $("spin").style.display = "none";
    $("title").textContent = "통합 로그인을 완료하지 못했습니다";
    $("msg").textContent = "";
    var e = $("err");
    e.innerHTML = "";
    e.appendChild(document.createTextNode(text + " "));
    var a = document.createElement("a");
    a.href = "/login";
    a.textContent = "로그인 화면으로";
    e.appendChild(a);
    e.style.display = "block";
  }
  function go(url) { done = true; window.location.href = url; }
  function toNls(nlsUrl) {
    var base = nlsUrl || LOGIN_URL;
    if (!base) { showError("SSO 로그인 페이지 주소가 없습니다."); return; }
    go(base + (base.indexOf("?") >= 0 ? "&" : "?") + "UURL=" + encodeURIComponent(CALLBACK_URL) + "&RTOA=1");
  }

  if (!NONCE) { showError("로그인 요청 정보(nonce)가 없습니다. 다시 시도해 주세요."); return; }

  // 개발 전용 흉내 (서버 NC_SSO_VERIFIER=stub 일 때만 stub=1)
  if (params.get("stub") === "1") {
    $("spin").style.display = "none";
    $("title").textContent = "개발용 SSO";
    $("msg").textContent = "NC 에이전트 없이 사번으로 SSO 흐름을 시험합니다(운영에서는 쓰지 않음).";
    var f = $("stub");
    f.style.display = "block";
    f.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var emp = $("stub-emp").value.trim();
      if (!/^[0-9A-Za-z]{1,20}$/.test(emp)) return;
      var ticket = "stub:" + emp + ":" + $("stub-toa").value + ":" + NONCE;
      go(CALLBACK_URL + "?ticket=" + encodeURIComponent(ticket));
    });
    return;
  }

  if (typeof window.Nexess_GetConnectNLSURL !== "function") {
    showError("통합 로그인 스크립트(NexessDemonFunc.js)를 불러오지 못했습니다. 관리자에게 SSO 배포 상태를 문의하세요.");
    return;
  }
  window.setTimeout(function () {
    showError("통합 로그인 에이전트가 응답하지 않습니다(10초). PC 의 NC 에이전트 실행 여부를 확인하세요.");
  }, 10000);

  try {
    window.Nexess_GetConnectNLSURL(function (r) {
      var nls = r && r.msg;
      window.Nexess_IsLogin(function (d) {
        if (!d || d.msg == 0) { toNls(nls); return; } // 미로그인 → NLS 로그인 후 콜백으로(서버가 한 번 다시 시작)
        window.Nexess_GetLoginToa(function () {
          window.Nexess_PrepareResession(function (p) {
            if (!p || p.resultCode != "1") { showError("통합 로그인 세션 준비에 실패했습니다(PrepareResession)."); return; }
            window.Nexess_GetTicketWithNonce(function (t) {
              var ticket = t && t.msg;
              if (!ticket || ticket.length == 1) { toNls(nls); return; }
              ticket = String(ticket).replace(/\+/g, "%2b"); // '+' 보존 (가이드 필수)
              go(CALLBACK_URL + "?ticket=" + escape(ticket) + "&nlsurl=" + encodeURIComponent(nls || ""));
            }, NONCE);
          }, NONCE);
        });
      });
    });
  } catch (e) {
    showError("통합 로그인 에이전트 호출 중 오류가 났습니다.");
  }
})();
