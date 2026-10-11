/**
 * web 컨테이너 시작점 (B.33) — Next standalone server.js 를 감싸 전달 헤더를 바로잡는다.
 *
 * Next 는 X-Forwarded-For 가 이미 있으면 덮지 않고 그대로 백엔드로 넘긴다. 사용자가 이 헤더를 직접 보내면
 * 위조한 IP 가 속도 제한 · 감사 기록에 쓰인다. 그래서 요청을 받자마자 실제 접속 주소로 바꾸고,
 * X-Forwarded-Host · X-Real-IP 도 지운다(Next 가 Host 로 다시 채운다).
 * 앞에 사내 L7 프록시(로드밸런서)가 있어 그 프록시가 X-Forwarded-For 를 채우면 TRUST_UPSTREAM_PROXY=1 로 유지한다.
 */
const http = require("node:http");

if (process.env.TRUST_UPSTREAM_PROXY !== "1") {
  const emit = http.Server.prototype.emit;
  http.Server.prototype.emit = function patchedEmit(event, req, ...rest) {
    if (event === "request" && req && req.headers) {
      const addr = req.socket && req.socket.remoteAddress;
      if (addr) req.headers["x-forwarded-for"] = addr;
      else delete req.headers["x-forwarded-for"];
      delete req.headers["x-forwarded-host"];
      delete req.headers["x-real-ip"];
    }
    return emit.call(this, event, req, ...rest);
  };
}

require("./server.js");
