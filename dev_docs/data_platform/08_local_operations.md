# 로컬 운영 원칙

## 팀원

기존 `start-console.cmd` 또는 `start-console.sh`를 사용하고 Console에서 Collection 기능만 실행한다. 세부 명령은 `dev_docs/runscript.md`를 따른다.

## 플랫폼 관리자

Collector와 Platform을 Docker Compose profile로 분리한다.

```bash
docker compose --profile collector up -d
docker compose --profile platform up -d
```

팀원 `.env`에는 pipeline metadata와 Backend credential을 제공하지 않는다. Docker socket 기반 Console은 로컬 신뢰 환경에서만 사용하고 외부에 공개하지 않는다.
