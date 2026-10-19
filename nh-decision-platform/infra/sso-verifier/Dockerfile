# 사내 SSO 티켓 검증기 (Phase R) — 벤더 jar 없이 빌드하고, 실행할 때 /app/libs/*.jar(볼륨)를 읽는다.
ARG JDK_IMAGE=eclipse-temurin:21-jdk
ARG JRE_IMAGE=eclipse-temurin:21-jre
FROM ${JDK_IMAGE} AS build
WORKDIR /src
COPY src/ ./src/
RUN javac --release 21 -d /out src/*.java

FROM ${JRE_IMAGE}
RUN useradd -r -u 10002 verifier && mkdir -p /app/libs && chown -R verifier /app
WORKDIR /app
COPY --from=build /out/ /app/classes/
USER verifier
EXPOSE 8090
HEALTHCHECK --interval=20s --timeout=5s --retries=5 CMD ["sh", "-c", "exec 3<>/dev/tcp/127.0.0.1/${PORT:-8090}"]
CMD ["sh", "-c", "exec java -cp '/app/classes:/app/libs/*' NcVerifierServer"]
