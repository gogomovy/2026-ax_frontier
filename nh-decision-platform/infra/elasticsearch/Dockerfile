# 선택 검색 엔진 Elasticsearch (설계 §21.18) — 한국어 형태소 분석기(nori)를 넣은 이미지.
# docker compose --profile search up -d elasticsearch  (또는 .env 에 COMPOSE_PROFILES=search)
# 버전은 ES_VERSION 으로 고정한다(올릴 때는 .env 에서). 다이제스트로 고정하려면 ES_IMAGE_BASE 에 repo@sha256:... 를 넣는다.
ARG ES_IMAGE_BASE=docker.elastic.co/elasticsearch/elasticsearch:9.5.4
FROM ${ES_IMAGE_BASE}
RUN bin/elasticsearch-plugin install --batch analysis-nori
