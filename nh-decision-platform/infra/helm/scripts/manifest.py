#!/usr/bin/env python3
"""반입 묶음 매니페스트 — images/*.tar 를 열어 이미지 이름 · ID · 체크섬 · values 키를 MANIFEST.md · manifest.json 으로 적는다.

    python3 infra/helm/scripts/manifest.py dist/nhdip-closed-1.0.0

bundle.sh 가 묶음 끝에 부른다. 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

# 원래 이미지 이름 → (values 키, 쓰는 워크로드, 켜는 조건)
ROLES = {
    "nhdip/api": ("images.api", "Deployment api · Deployment worker (초기화 컨테이너 files-init · wait-api 포함)", "항상"),
    "nhdip/web": ("images.web", "Deployment web", "항상"),
    "nhdip/elasticsearch": ("images.elasticsearch", "StatefulSet elasticsearch (초기화 컨테이너 chown · sysctl 포함)", "elasticsearch.enabled (기본 true)"),
    "nhdip/sso-verifier": ("images.ssoVerifier", "Deployment sso-verifier", "ssoVerifier.enabled (사내 SSO)"),
    "pgvector/pgvector": ("images.postgres", "StatefulSet postgres", "postgres.enabled (기본 true)"),
    "neo4j": ("images.neo4j", "StatefulSet neo4j", "neo4j.enabled (기본 true)"),
    "berriai/litellm": ("images.litellm", "Deployment litellm", "litellm.enabled (기본 false)"),
}


def short_ref(ref: str) -> str:
    """docker load 가 보여 주는 이름 — docker.io/ · library/ 를 뗀다."""
    for p in ("docker.io/library/", "docker.io/", "index.docker.io/library/", "index.docker.io/"):
        if ref.startswith(p):
            return ref[len(p):]
    return ref


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_image(p: Path) -> dict:
    with tarfile.open(p) as t:
        man = json.load(t.extractfile("manifest.json"))[0]
        cfg_raw = t.extractfile(man["Config"]).read()
    cfg = json.loads(cfg_raw)
    c = cfg.get("config") or {}
    tags = man.get("RepoTags") or []
    ref = short_ref(tags[0]) if tags else ""
    repo, _, tag = ref.rpartition(":")
    return {
        "file": p.name,
        "image": ref,
        "repository": repo,
        "tag": tag,
        "imageId": "sha256:" + hashlib.sha256(cfg_raw).hexdigest(),
        "os": cfg.get("os"),
        "arch": cfg.get("architecture"),
        "created": cfg.get("created"),
        "layers": len(man.get("Layers") or []),
        "user": c.get("User") or "(root)",
        "entrypoint": c.get("Entrypoint"),
        "cmd": c.get("Cmd"),
        "ports": sorted((c.get("ExposedPorts") or {}).keys()),
        "sizeBytes": p.stat().st_size,
        "sha256": sha256_file(p),
    }


def main(out: Path) -> None:
    imgs = [read_image(p) for p in sorted((out / "images").glob("*.tar"))]
    order = list(ROLES)
    imgs.sort(key=lambda i: order.index(i["repository"]) if i["repository"] in order else len(order))
    for i in imgs:
        key, workload, cond = ROLES.get(i["repository"], ("-", "-", "-"))
        i.update(valuesKey=key, workload=workload, enabledWhen=cond)
    version = {}
    vf = out / "VERSION"
    if vf.exists():
        version = dict(line.split("=", 1) for line in vf.read_text(encoding="utf-8").splitlines() if "=" in line)
    charts = sorted(p.name for p in (out / "chart").glob("*.tgz"))
    (out / "images" / "images.txt").write_text("".join(f"{i['file']} {i['image']}\n" for i in imgs), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"version": version, "chart": charts, "images": imgs}, ensure_ascii=False, indent=2), encoding="utf-8")

    gb = lambda n: f"{n / (1 << 30):.2f} GB" if n >= 1 << 30 else f"{n / (1 << 20):.0f} MB"  # noqa: E731
    total = sum(i["sizeBytes"] for i in imgs)
    L = [
        "# 반입 묶음 매니페스트 — NH NAVI (nhdip)",
        "",
        f"- 태그 `{version.get('tag', '-')}` · 커밋 `{version.get('commit', '-')}` · 플랫폼 `{version.get('platform', 'linux/amd64')}` · 만든 시각 {version.get('built', datetime.now(timezone.utc).isoformat(timespec='seconds'))}",
        f"- 헬름 차트: {', '.join(f'`chart/{c}`' for c in charts) or '-'}",
        f"- 이미지 {len(imgs)}개 · 합계 {gb(total)}",
        "",
        "## 1. 이미지 목록",
        "",
        "`docker load -i images/<tar 파일>` 하면 아래 **원래 이름** 으로 들어옵니다. Nexus 에 올린 경로를 values-closed.yaml 의 **values 키** 에 적습니다.",
        "",
        "| tar 파일 | 원래 이름 (docker load 후) | values 키 | 쓰는 곳 | 켜는 조건 | 크기 |",
        "|---|---|---|---|---|---|",
    ]
    L += [f"| `images/{i['file']}` | `{i['image']}` | `{i['valuesKey']}` | {i['workload']} | {i['enabledWhen']} | {gb(i['sizeBytes'])} |" for i in imgs]
    L += ["", "## 2. 이미지 세부 (무결성 확인용)", ""]
    for i in imgs:
        L += [
            f"### `{i['image']}`",
            "",
            f"- 이미지 ID(설정 다이제스트): `{i['imageId']}` — docker 기본 저장소면 load 뒤 `docker image inspect {i['image']} --format '{{{{.Id}}}}'` 와 같음(containerd 이미지 저장소는 매니페스트 다이제스트를 보여 줘 다를 수 있음)",
            f"- tar SHA256: `{i['sha256']}`",
            f"- {i['os']}/{i['arch']} · 레이어 {i['layers']}개 · 실행 계정 `{i['user']}` · 만든 시각 {i['created']}",
            f"- 시작 명령: entrypoint `{json.dumps(i['entrypoint'], ensure_ascii=False)}` · cmd `{json.dumps(i['cmd'], ensure_ascii=False)}` · 포트 {', '.join(i['ports']) or '-'}",
            "",
        ]
    L += [
        "## 3. Nexus 에 올리기 (예)",
        "",
        "```bash",
        "NEXUS=<Nexus 호스트:포트>/<저장소 경로>     # 예: nexus.example.local:5000/nhnavi",
        "docker login <Nexus 호스트:포트>",
    ]
    for i in imgs:
        L += [f"docker load -i images/{i['file']} && docker tag {i['image']} $NEXUS/{i['image']} && docker push $NEXUS/{i['image']}"]
    L += [
        "```",
        "",
        "또는 `bash scripts/push-images.sh $NEXUS` (같은 이름 규칙으로 전체를 올리고, 적을 경로를 보여 줌).",
        "",
        "## 4. values-closed.yaml 에 적을 값 (위 규칙으로 올렸을 때)",
        "",
        "```yaml",
        "images:",
    ]
    for i in imgs:
        k = i["valuesKey"].split(".", 1)[-1]
        L += [f"  {k}: {{repository: \"<NEXUS>/{i['repository']}\", tag: \"{i['tag']}\"}}"]
    L += [
        "```",
        "",
        "다른 경로 · 이름으로 올렸다면 `repository` 를 실제 경로로(태그 앞까지), 태그를 바꿨다면 `tag` 를 바꿉니다.",
        "",
        "## 5. 무결성 확인",
        "",
        "```bash",
        "sha256sum -c SHA256SUMS    # 묶음 전체 파일",
        "```",
        "",
    ]
    (out / "MANIFEST.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[manifest] 이미지 {len(imgs)}개 → {out / 'MANIFEST.md'} · {out / 'manifest.json'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용법: python3 manifest.py <묶음 폴더>")
    main(Path(sys.argv[1]))
