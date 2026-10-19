{{/* ── 이름 · 라벨 ───────────────────────────────────────────── */}}
{{- define "nhdip.commonLabels" -}}
app.kubernetes.io/part-of: nhdip
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{- define "nhdip.labels" -}}
{{ include "nhdip.commonLabels" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* 선택 라벨 — dict "root" . "component" "api" */}}
{{- define "nhdip.selector" -}}
app.kubernetes.io/name: {{ .component }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end }}

{{- define "nhdip.componentLabels" -}}
{{ include "nhdip.commonLabels" .root }}
{{ include "nhdip.selector" . }}
{{- end }}

{{/* ── 이미지 — dict "root" . "image" .Values.images.api "name" "api" "own" true
     repository 는 Nexus 에 올린 경로를 그대로 적는다(global.imageRegistry 는 선택 — 채우면 앞에 붙인다) ── */}}
{{- define "nhdip.image" -}}
{{- $g := .root.Values.global -}}
{{- if not .image.repository -}}
{{- fail (printf "[필수] images.%s.repository — Nexus 에 올린 이미지 경로(태그 앞까지)를 values-closed.yaml 에 적으세요 (예: nexus.example.local:5000/<저장소 경로>/<이미지 이름>)" .name) -}}
{{- end -}}
{{- $tag := .image.tag -}}
{{- if not $tag -}}
{{- if .own -}}{{- $tag = $g.imageTag | default .root.Chart.AppVersion -}}{{- else -}}{{- fail (printf "[필수] images.%s.tag 가 비었습니다" .name) -}}{{- end -}}
{{- end -}}
{{- $reg := trimSuffix "/" ($g.imageRegistry | default "") -}}
{{- if $reg -}}{{ printf "%s/%s:%s" $reg .image.repository (toString $tag) }}{{- else -}}{{ printf "%s:%s" .image.repository (toString $tag) }}{{- end -}}
{{- end }}

{{/* ── 파드 공통 (노드 지정 · 받기 Secret · 서비스 링크 끄기) ── */}}
{{- define "nhdip.podCommon" -}}
enableServiceLinks: false
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- with .Values.global.nodeSelector }}
nodeSelector:
{{ toYaml . | indent 2 }}
{{- end }}
{{- with .Values.global.tolerations }}
tolerations:
{{ toYaml . | indent 2 }}
{{- end }}
{{- end }}

{{/* ── Secret 값 — dict "root" . "key" "POSTGRES_PASSWORD" "name" "ENV 이름(기본 key)" "optional" false ── */}}
{{- define "nhdip.secretEnv" -}}
- name: {{ .name | default .key }}
  valueFrom:
    secretKeyRef:
      name: {{ .root.Values.secrets.name }}
      key: {{ .key }}
      {{- if .optional }}
      optional: true
      {{- end }}
{{- end }}

{{/* ── 데이터 볼륨 — hostPathBase 가 있으면 서버 디렉터리, 없으면 PVC. dict "root" . "dir" "pgdata" ── */}}
{{- define "nhdip.pvcName" -}}
{{ printf "%s-%s" .root.Release.Name .dir }}
{{- end }}

{{- define "nhdip.dataVolume" -}}
{{- $base := trimSuffix "/" (.root.Values.persistence.hostPathBase | default "") -}}
{{- if $base }}
hostPath:
  path: {{ printf "%s/%s" $base .dir }}
  type: DirectoryOrCreate
{{- else }}
persistentVolumeClaim:
  claimName: {{ include "nhdip.pvcName" . }}
{{- end }}
{{- end }}

{{/* ── 밖에서 넣는 파일(벤더 JS · jar) — {hostPath | configMap | existingClaim} ── */}}
{{- define "nhdip.extVolume" -}}
{{- if .configMap }}
configMap:
  name: {{ .configMap }}
{{- else if .existingClaim }}
persistentVolumeClaim:
  claimName: {{ .existingClaim }}
  readOnly: true
{{- else if .hostPath }}
hostPath:
  path: {{ .hostPath }}
  type: Directory
{{- end }}
{{- end }}

{{/* ── 주소 ─────────────────────────────────────────────────── */}}
{{- define "nhdip.publicUrl" -}}
{{- if .Values.app.publicUrl -}}
{{ trimSuffix "/" .Values.app.publicUrl }}
{{- else if .Values.ingress.host -}}
{{ printf "%s://%s" (ternary "https" "http" (and .Values.ingress.enabled .Values.ingress.tls.enabled)) .Values.ingress.host }}
{{- end -}}
{{- end }}

{{- define "nhdip.cookieSecure" -}}
{{- $v := toString .Values.app.cookieSecure -}}
{{- if eq $v "" -}}{{ ternary "1" "0" (hasPrefix "https://" (include "nhdip.publicUrl" .)) }}{{- else if has $v (list "true" "1" "yes") -}}1{{- else -}}0{{- end -}}
{{- end }}

{{- define "nhdip.dbHost" -}}
{{- if .Values.postgres.enabled -}}postgres{{- else -}}{{ .Values.postgres.external.host }}{{- end -}}
{{- end }}

{{- define "nhdip.dbPort" -}}
{{- if .Values.postgres.enabled -}}5432{{- else -}}{{ .Values.postgres.external.port | default 5432 }}{{- end -}}
{{- end }}

{{- define "nhdip.esUrl" -}}
{{- if .Values.elasticsearch.enabled -}}http://elasticsearch:9200{{- else -}}{{ .Values.elasticsearch.externalUrl }}{{- end -}}
{{- end }}

{{- define "nhdip.neo4jUri" -}}
{{- if .Values.neo4j.enabled -}}bolt://neo4j:7687{{- else -}}{{ .Values.neo4j.externalUri }}{{- end -}}
{{- end }}

{{/* ── api · worker 공통 환경변수 (docker-compose x-api-env 와 같은 항목) ── */}}
{{- define "nhdip.apiEnv" -}}
{{- $v := .Values -}}
- name: TZ
  value: {{ $v.global.timezone | quote }}
- name: NHDIP_ENV
  value: {{ $v.app.env | quote }}
{{ include "nhdip.secretEnv" (dict "root" . "key" "POSTGRES_PASSWORD") }}
- name: DATABASE_URL
  value: {{ printf "postgresql+psycopg://%s:$(POSTGRES_PASSWORD)@%s:%s/%s" $v.postgres.user (include "nhdip.dbHost" .) (include "nhdip.dbPort" .) $v.postgres.database | quote }}
- name: NEO4J_URI
  value: {{ include "nhdip.neo4jUri" . | quote }}
- name: NEO4J_USER
  value: neo4j
{{ include "nhdip.secretEnv" (dict "root" . "key" "NEO4J_PASSWORD") }}
- name: FILESTORE_DIR
  value: /data/files
{{ include "nhdip.secretEnv" (dict "root" . "key" "SESSION_SECRET") }}
{{ include "nhdip.secretEnv" (dict "root" . "key" "CONFIG_ENC_KEY") }}
- name: COOKIE_SECURE
  value: {{ include "nhdip.cookieSecure" . | quote }}
- name: TRUSTED_ORIGINS
  value: {{ $v.app.trustedOrigins | default (include "nhdip.publicUrl" .) | quote }}
- name: TRUSTED_PROXIES
  value: {{ $v.app.trustedProxies | quote }}
- name: TRUSTED_PROXY_HOPS
  value: {{ $v.app.trustedProxyHops | quote }}
- name: API_DOCS
  value: {{ $v.app.apiDocs | quote }}
- name: DB_IDLE_TX_TIMEOUT_MS
  value: {{ $v.app.dbIdleTxTimeoutMs | quote }}
- name: BOOTSTRAP_ADMIN_EMP_NO
  value: {{ $v.app.bootstrapAdminEmpNo | quote }}
{{ include "nhdip.secretEnv" (dict "root" . "key" "BOOTSTRAP_ADMIN_PASSWORD") }}
- name: LLM_DEFAULT_BASE_URL
  value: {{ $v.app.llm.baseUrl | quote }}
- name: LLM_DEFAULT_MODEL
  value: {{ $v.app.llm.model | quote }}
{{ include "nhdip.secretEnv" (dict "root" . "key" "LLM_DEFAULT_API_KEY" "optional" true) }}
{{ include "nhdip.secretEnv" (dict "root" . "key" "DEMO_USER_PASSWORD" "optional" true) }}
- name: UPLOAD_AV_COMMAND
  value: {{ $v.app.uploadAvCommand | quote }}
- name: OIDC_ISSUER
  value: {{ $v.app.oidc.issuer | quote }}
- name: OIDC_CLIENT_ID
  value: {{ $v.app.oidc.clientId | quote }}
{{ include "nhdip.secretEnv" (dict "root" . "key" "OIDC_CLIENT_SECRET" "optional" true) }}
- name: OIDC_REDIRECT_URI
  value: {{ $v.app.oidc.redirectUri | default (ternary (printf "%s/backend/auth/oidc/callback" (include "nhdip.publicUrl" .)) "" (ne $v.app.oidc.issuer "")) | quote }}
- name: OIDC_EMP_CLAIM
  value: {{ $v.app.oidc.empClaim | quote }}
- name: OIDC_LOCAL_LOGIN
  value: {{ $v.app.oidc.localLogin | quote }}
- name: NC_SSO_ENABLED
  value: {{ ternary "1" "0" $v.app.ncSso.enabled | quote }}
- name: NC_SSO_LABEL
  value: {{ $v.app.ncSso.label | quote }}
- name: NC_SSO_LOGIN_URL
  value: {{ $v.app.ncSso.loginUrl | quote }}
- name: NC_SSO_ALLOWED_TOA
  value: {{ $v.app.ncSso.allowedToa | quote }}
- name: NC_SSO_VERIFIER
  value: http
- name: NC_SSO_VERIFIER_URL
  value: http://sso-verifier:8090
{{ include "nhdip.secretEnv" (dict "root" . "key" "NC_SSO_VERIFIER_TOKEN" "optional" true) }}
- name: NC_SSO_LOCAL_LOGIN
  value: {{ $v.app.ncSso.localLogin | quote }}
- name: NC_SSO_ASSETS_DIR
  value: /opt/nc-js
{{ include "nhdip.secretEnv" (dict "root" . "key" "ALERT_WEBHOOK_URL" "optional" true) }}
- name: ALERT_SMTP_HOST
  value: {{ $v.app.alerts.smtp.host | quote }}
- name: ALERT_SMTP_PORT
  value: {{ $v.app.alerts.smtp.port | quote }}
- name: ALERT_SMTP_USER
  value: {{ $v.app.alerts.smtp.user | quote }}
{{ include "nhdip.secretEnv" (dict "root" . "key" "ALERT_SMTP_PASSWORD" "optional" true) }}
- name: ALERT_SMTP_FROM
  value: {{ $v.app.alerts.smtp.from | quote }}
- name: ALERT_SMTP_TO
  value: {{ $v.app.alerts.smtp.to | quote }}
- name: ALERT_SMTP_STARTTLS
  value: {{ ternary "1" "0" $v.app.alerts.smtp.starttls | quote }}
- name: ES_URL
  value: {{ include "nhdip.esUrl" . | quote }}
- name: ES_USER
  value: {{ $v.elasticsearch.user | quote }}
{{ include "nhdip.secretEnv" (dict "root" . "key" "ES_PASSWORD" "optional" true) }}
- name: ES_INDEX
  value: {{ $v.app.esIndex | quote }}
- name: ES_DOC_INDEX
  value: {{ $v.app.esDocIndex | quote }}
{{- with $v.app.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/* ── 설치 전 점검 — 비어 있으면 무엇을 채울지 알려 주고 멈춘다 ── */}}
{{- define "nhdip.validate" -}}
{{- $v := .Values -}}
{{- if and (not $v.global.nodeSelector) (not $v.global.allowAnyNode) -}}
{{- fail "[필수] global.nodeSelector — 띄울 서버를 지정하세요 (예: {kubernetes.io/hostname: <노드 이름>} · kubectl get nodes --show-labels)" -}}
{{- end -}}
{{- range $k, $val := $v.global.nodeSelector -}}
{{- if not $val -}}{{- fail (printf "[필수] global.nodeSelector.%s 값이 비었습니다 — 띄울 서버(노드) 이름을 적으세요 (kubectl get nodes)" $k) -}}{{- end -}}
{{- end -}}
{{- if and (not $v.persistence.hostPathBase) (not $v.persistence.storageClass) (not $v.persistence.useDefaultStorageClass) -}}
{{- fail "[필수] 저장소 — persistence.hostPathBase(서버 디렉터리, 예: /data/nhdip) 또는 persistence.storageClass(kubectl get storageclass) 중 하나를 채우세요 (클러스터 기본 저장소 클래스를 쓰려면 persistence.useDefaultStorageClass=true)" -}}
{{- end -}}
{{- if $v.ingress.enabled -}}
{{- if not $v.ingress.host -}}{{- fail "[필수] ingress.host — 접속 도메인을 적으세요 (예: nhnavi.example.local)" -}}{{- end -}}
{{- if not $v.ingress.className -}}{{- fail "[필수] ingress.className — 인그레스 클래스를 적으세요 (kubectl get ingressclass, 예: nginx)" -}}{{- end -}}
{{- if and $v.ingress.tls.enabled (not $v.ingress.tls.secretName) -}}{{- fail "[필수] ingress.tls.secretName — TLS 인증서 Secret 이름 (인증서를 앞단 L7 에서 끝내면 ingress.tls.enabled=false · app.publicUrl=https://<도메인>)" -}}{{- end -}}
{{- end -}}
{{- if and (not $v.postgres.enabled) (not $v.postgres.external.host) -}}
{{- fail "postgres.enabled=false 이면 postgres.external.host (사내 PostgreSQL 주소)가 필요합니다" -}}
{{- end -}}
{{- if and (not $v.neo4j.enabled) (not $v.neo4j.externalUri) -}}
{{- fail "neo4j.enabled=false 이면 neo4j.externalUri (예: bolt://neo4j.internal:7687)가 필요합니다" -}}
{{- end -}}
{{- if $v.app.ncSso.enabled -}}
{{- if not $v.ssoVerifier.enabled -}}{{- fail "app.ncSso.enabled=true 이면 ssoVerifier.enabled=true 도 필요합니다 (티켓 검증기)" -}}{{- end -}}
{{- $a := $v.app.ncSso.assets -}}
{{- if not (or $a.hostPath $a.configMap $a.existingClaim) -}}{{- fail "[필수 · 사내 SSO] app.ncSso.assets — 벤더 JS 위치(hostPath · configMap · existingClaim 중 하나)" -}}{{- end -}}
{{- end -}}
{{- if $v.ssoVerifier.enabled -}}
{{- $l := $v.ssoVerifier.libs -}}
{{- if not (or $l.hostPath $l.existingClaim) -}}{{- fail "[필수 · 사내 SSO] ssoVerifier.libs — 벤더 jar 위치(hostPath · existingClaim 중 하나)" -}}{{- end -}}
{{- end -}}
{{- if and $v.litellm.enabled (not $v.postgres.enabled) -}}
{{- fail "litellm.enabled=true 는 내장 postgres(litellm DB 를 처음 기동 때 만든다)와 함께만 씁니다" -}}
{{- end -}}
{{- end }}
