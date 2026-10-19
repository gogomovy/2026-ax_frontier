import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;

/**
 * 사내 SSO 티켓 검증기 (Phase R · 가이드 SSO-ORG-SYNC-INTEGRATION-GUIDE §2-4 NcTicketVerifierImpl 이식).
 *
 * INISAFE Nexess 티켓(encNonce&&encSKIPAndTime&&encIDAndTOA)을 벤더 jar(com.initech.eam.nls.TicketV3)로 풀어
 * 개인번호(사번) · TOA 를 돌려준다. 파이썬 API 는 이 서비스만 부른다 — 벤더 jar · 암호 키는 이 컨테이너 밖으로 나가지 않는다.
 *
 *   POST /verify   (application/x-www-form-urlencoded: ticket, nonce) + 헤더 X-Verifier-Token
 *                  → 200 {"ok":true,"ssoId":"…","toa":3} | 400 {"ok":false,"error":"verify_failed|nonce","detail":"…"} | 401
 *   GET  /health   → 200 {"ok":true,"provider":true}  (벤더 jar 를 읽지 못했으면 503)
 *
 * 벤더 클래스는 리플렉션으로 부른다 — 이미지는 jar 없이 빌드되고, 실행할 때 /app/libs/*.jar(볼륨)를 클래스패스에 둔다.
 * 환경변수: PORT(기본 8090) · VERIFIER_TOKEN(필수, 16자 이상) · BIND(기본 0.0.0.0 — 컴포즈 내부망에서만 열 것)
 */
public final class NcVerifierServer {
    private static Method decryptNonce;
    private static Method readIdAndToa;
    private static String providerError;
    private static byte[] token;

    public static void main(String[] args) throws Exception {
        String t = env("VERIFIER_TOKEN", "");
        if (t.length() < 16) {
            System.err.println("[sso-verifier] VERIFIER_TOKEN(16자 이상)이 필요합니다");
            System.exit(2);
        }
        token = t.getBytes(StandardCharsets.UTF_8);
        init();
        int port = Integer.parseInt(env("PORT", "8090"));
        HttpServer server = HttpServer.create(new InetSocketAddress(env("BIND", "0.0.0.0"), port), 0);
        server.createContext("/health", NcVerifierServer::health);
        server.createContext("/verify", NcVerifierServer::verify);
        server.setExecutor(Executors.newFixedThreadPool(Integer.parseInt(env("THREADS", "8"))));
        server.start();
        System.out.println("[sso-verifier] listening :" + port + (providerError == null ? "" : " (벤더 jar 오류: " + providerError + ")"));
    }

    private static String env(String k, String d) {
        String v = System.getenv(k);
        return v == null || v.isEmpty() ? d : v;
    }

    /** 가이드 NcTicketVerifierImpl.init — JCE Provider 등록 + TicketV3 메서드 찾기 */
    private static void init() {
        try {
            Class<?> provider = Class.forName("com.initech.provider.crypto.InitechProvider");
            provider.getMethod("addAsProvider", boolean.class, boolean.class).invoke(null, false, false);
            Class<?> ticket = Class.forName("com.initech.eam.nls.TicketV3");
            decryptNonce = ticket.getMethod("decryptNonce", String.class, String.class);
            readIdAndToa = ticket.getMethod("readIDAndTOA", String.class, String.class);
        } catch (ClassNotFoundException e) {
            providerError = "클래스 없음 " + e.getMessage() + " — /app/libs 에 external_v4.2.1.00_NHBank14.jar · INICrypto_v4.2.10.jar · INISAFEToolSet_v1.1.1.jar · jdom2 · log4j 를 넣으세요";
        } catch (Exception e) {
            providerError = e.getClass().getSimpleName() + ": " + e.getMessage();
        }
        if (providerError != null) System.err.println("[sso-verifier] " + providerError);
    }

    private static void health(HttpExchange ex) throws IOException {
        if (providerError != null) {
            send(ex, 503, "{\"ok\":false,\"provider\":false,\"detail\":" + q(providerError) + "}");
        } else {
            send(ex, 200, "{\"ok\":true,\"provider\":true}");
        }
    }

    private static void verify(HttpExchange ex) throws IOException {
        if (!"POST".equals(ex.getRequestMethod())) {
            send(ex, 405, "{\"ok\":false,\"error\":\"method\"}");
            return;
        }
        String got = ex.getRequestHeaders().getFirst("X-Verifier-Token");
        if (got == null || !MessageDigest.isEqual(token, got.getBytes(StandardCharsets.UTF_8))) {
            send(ex, 401, "{\"ok\":false,\"error\":\"unauthorized\"}");
            return;
        }
        if (providerError != null) {
            send(ex, 503, "{\"ok\":false,\"error\":\"provider\",\"detail\":" + q(providerError) + "}");
            return;
        }
        Map<String, String> form = parseForm(readBody(ex.getRequestBody(), 64 * 1024));
        try {
            String[] r = decode(form.getOrDefault("ticket", ""), form.get("nonce"));
            send(ex, 200, "{\"ok\":true,\"ssoId\":" + q(r[0]) + ",\"toa\":" + Integer.parseInt(r[1]) + "}");
        } catch (VerifyException e) {
            send(ex, 400, "{\"ok\":false,\"error\":" + q(e.code) + ",\"detail\":" + q(e.getMessage()) + "}");
        } catch (Exception e) {
            send(ex, 400, "{\"ok\":false,\"error\":\"verify_failed\",\"detail\":" + q(e.getClass().getSimpleName()) + "}");
        }
    }

    /** 가이드 NcTicketVerifierImpl.verify 와 같은 순서 — 반환 {사번, TOA} */
    static String[] decode(String ticket, String nonce) throws Exception {
        String decoded = URLDecoder.decode(ticket, StandardCharsets.UTF_8);
        int first = decoded.indexOf("&&");
        int second = decoded.lastIndexOf("&&");
        if (first < 0 || second < 0 || second <= first) throw new VerifyException("verify_failed", "티켓 형식 오류");
        String encNonce = strip(decoded.substring(0, first));
        String encSkipAndTime = strip(decoded.substring(first + 2, second));
        String encIdAndToa = strip(decoded.substring(second + 2));
        String decNonce = cutCarriageReturn((String) call(decryptNonce, encSkipAndTime, encNonce));
        String clean = nonce == null ? null : strip(nonce);
        // 가이드 원본은 콜백에서 nonce 를 넘기지 않아 대조를 건너뛰었다(알려진 문제 1) — 여기서는 비어 있으면 거부
        if (clean == null || clean.isEmpty() || !MessageDigest.isEqual(clean.getBytes(StandardCharsets.UTF_8), decNonce.getBytes(StandardCharsets.UTF_8))) {
            throw new VerifyException("nonce", "nonce 불일치");
        }
        @SuppressWarnings("unchecked")
        List<Object> res = (List<Object>) call(readIdAndToa, encSkipAndTime, encIdAndToa);
        String userId = res == null || res.isEmpty() ? null : (String) res.get(0);
        String toa = res == null || res.size() < 2 ? null : String.valueOf(res.get(1)).trim();
        if (userId == null || userId.isBlank() || toa == null || !toa.matches("\\d{1,4}")) throw new VerifyException("verify_failed", "사번 · TOA 없음");
        return new String[] {userId.trim(), toa};
    }

    private static Object call(Method m, String a, String b) throws Exception {
        try {
            return m.invoke(null, a, b);
        } catch (InvocationTargetException e) {
            Throwable c = e.getCause();
            throw c instanceof Exception ? (Exception) c : new Exception(c);
        }
    }

    /** 리터럴 "\r" · "\n" 두 글자 제거 (실제 개행 아님 — 가이드 주석) */
    private static String strip(String s) {
        return s.replace("\\r", "").replace("\\n", "");
    }

    private static String cutCarriageReturn(String s) {
        if (s == null) return "";
        int idx = s.indexOf("\\n");
        while (idx != -1) {
            String head = s.substring(0, idx);
            s = (idx != s.length() - 1) ? head + s.substring(Math.min(s.length(), idx + 2)) : head;
            idx = s.indexOf("\\n");
        }
        return s;
    }

    private static String readBody(InputStream in, int max) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) > 0) {
            out.write(buf, 0, n);
            if (out.size() > max) throw new IOException("본문이 너무 큽니다");
        }
        return out.toString(StandardCharsets.UTF_8);
    }

    private static Map<String, String> parseForm(String body) {
        Map<String, String> out = new HashMap<>();
        for (String kv : body.split("&")) {
            int i = kv.indexOf('=');
            if (i <= 0) continue;
            // 폼 값은 한 번 풀어 받는다 — 티켓 안의 %2b 등은 decode() 에서 한 번 더 푼다(가이드와 같은 두 번 풀기)
            out.put(URLDecoder.decode(kv.substring(0, i), StandardCharsets.UTF_8), URLDecoder.decode(kv.substring(i + 1), StandardCharsets.UTF_8));
        }
        return out;
    }

    private static void send(HttpExchange ex, int status, String json) throws IOException {
        byte[] b = json.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, b.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(b);
        }
    }

    private static String q(String s) {
        if (s == null) return "null";
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') sb.append('\\').append(c);
            else if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
            else sb.append(c);
        }
        return sb.append('"').toString();
    }

    static final class VerifyException extends Exception {
        final String code;

        VerifyException(String code, String msg) {
            super(msg);
            this.code = code;
        }
    }
}
