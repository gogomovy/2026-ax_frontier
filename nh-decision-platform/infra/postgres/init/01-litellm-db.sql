-- 최초 기동 시 1회 실행 (postgres 공식 이미지 initdb 훅).
-- LiteLLM 게이트웨이의 가상 키·모델 등록 정보를 플랫폼 원장과 분리된 데이터베이스에 둔다.
CREATE DATABASE litellm;

-- 플랫폼 원장 데이터베이스에 벡터 확장을 미리 준비한다(마이그레이션에서도 IF NOT EXISTS 로 보장).
CREATE EXTENSION IF NOT EXISTS vector;
