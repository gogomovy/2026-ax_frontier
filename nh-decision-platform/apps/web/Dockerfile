# ─────────────────────────────────────────────────────────────
# NHDIP Web (Next.js standalone)
# ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund

FROM node:20-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_DATA_SOURCE=mock
ARG NEXT_PUBLIC_AS_OF=2026-08-31
# /backend/* 프록시 대상 — next.config rewrites 가 빌드 시점에 고정하므로 빌드 인자로 받는다
ARG API_INTERNAL_URL=http://api:8000
ENV NEXT_PUBLIC_DATA_SOURCE=$NEXT_PUBLIC_DATA_SOURCE \
    NEXT_PUBLIC_AS_OF=$NEXT_PUBLIC_AS_OF \
    API_INTERNAL_URL=$API_INTERNAL_URL \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# HOSTNAME 을 명시하지 않으면 Docker 가 주입한 컨테이너 ID 가 Next standalone 의
# bind 주소로 사용되어 loopback(127.0.0.1) 접근이 실패한다(healthcheck 실패 원인).
RUN addgroup -g 10001 -S nodejs && adduser -S -u 10001 -G nodejs nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
# 전달 헤더(X-Forwarded-For 등)를 실제 접속 주소로 바로잡는 시작점 (B.33)
COPY --chown=nextjs:nodejs server-entry.cjs ./server-entry.cjs
USER nextjs
EXPOSE 3000
CMD ["node", "server-entry.cjs"]
