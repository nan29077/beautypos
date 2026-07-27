# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ADPAY는 오프라인 가맹점을 위한 한국 핀테크 플랫폼으로, 결제 단말기 관리, 직원별 매출 귀속, 정산/수수료 관리, 광고 플랫폼, CRM, 영수증 리뷰 시스템을 제공한다.

## Commands

```bash
# 로컬 실행 (SQLite)
uvicorn app.main:app --reload --port 8000

# DB 초기화 및 시드 데이터 생성
python -m app.init_db

# Docker 실행 (MariaDB)
docker-compose up --build

# Alembic 마이그레이션
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Architecture

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Alembic, MariaDB(prod) / SQLite(dev), JWT 인증, Fernet 암호화

### 핵심 구조

- `main.py` — 루트 진입점, `app.main`을 import
- `app/main.py` — FastAPI 앱 정의, 모든 라우터 등록, 정적 파일 마운트, startup 시 `init_db()` 호출
- `app/config.py` — Pydantic Settings 기반 설정 (DB, JWT, OAuth, 암호화 키)
- `app/database.py` — SQLAlchemy engine, `SessionLocal`, `Base`, `get_db()` 의존성

### 인증 & 권한 (RBAC)

4개 역할: `ADMIN`, `SALES`, `OWNER`, `DESIGNER`

- `app/auth/jwt_handler.py` — 토큰 생성/검증, bcrypt 비밀번호 해싱
- `app/auth/dependencies.py` — `get_current_user` 미들웨어, `require_roles()` 데코레이터 팩토리
- 각 라우터는 `require_admin`, `require_sales`, `require_owner`, `require_designer` 사용
- 단말기 인증은 별도로 `X-Terminal-Key` 헤더 사용 (bcrypt 해시 또는 DEV_MODE에서 평문 비교)

### API 라우터 (app/api/)

| 라우터 | prefix | 역할 |
|--------|--------|------|
| auth_routes | /api/auth | 회원가입, 로그인, OAuth, test-login |
| admin_routes | /api/admin | 가맹점/PG/정산/광고/페이아웃 관리 |
| owner_routes | /api/owner | 가맹점주 대시보드, 직원/광고/리뷰 |
| sales_routes | /api/sales | 영업담당 가맹점 현황, 정산 요청 |
| designer_routes | /api/designer | 디자이너 매출/대시보드 |
| terminal_routes | /api/terminal | 단말기 거래 수신 |

### 서비스 (app/services/)

- `encryption.py` — Fernet 대칭 암호화 (PG 시크릿 저장용). ENCRYPTION_KEY의 SHA256 해시로 키 유도
- `pg_service.py` — PG사 Mock 구현 (seedpayments, kiwoompay, toss). 80% 성공률 시뮬레이션

### 주요 데이터 흐름

**거래 처리:** 단말기(X-Terminal-Key) → `POST /api/terminal/transactions` → staff_code로 직원 매칭 → Transaction 생성

**정산:** `POST /api/admin/settlements/calculate` → 기간별 거래 합산 → PG 수수료(FeePolicy) 차감 → 영업 커미션 계산 → Settlement 생성

**페이아웃:** Owner/Sales가 PayoutRequest 생성 → Admin이 승인/거절


### 환경 변수

로컬 개발 시 `.env` 파일 필요:
- `DATABASE_URL_OVERRIDE=sqlite:///./adpay.db` — SQLite 사용 시
- `JWT_SECRET_KEY` — JWT 서명 키
- `ENCRYPTION_KEY` — PG 시크릿 암호화 키
- `DEV_MODE=True` — test-login 활성화, 단말기 평문 키 허용
- OAuth 키는 선택사항 (KAKAO/NAVER/GOOGLE_CLIENT_ID/SECRET)

### 코드 컨벤션

- 모든 모델은 `Base` (DeclarativeBase) 상속, `app/models/__init__.py`에서 export
- 모든 라우트는 의존성 주입 사용: `Depends(get_db)`, `Depends(require_roles([...]))`
- 상태/역할 필드는 Enum 사용
- 민감 데이터는 `services.encryption`으로 암호화 저장, API 응답 시 `mask_value()`로 마스킹
- Decimal, datetime은 JSON 직렬화 시 문자열 변환
- 시드 데이터는 `app/seed.py`에서 idempotent하게 관리 (admin@test.com 존재 여부 체크)

### 테스트 계정 (시드 데이터)

| 이메일 | 비밀번호 | 역할 |
|--------|----------|------|
| admin@test.com | Test1234! | ADMIN |
| sales@test.com | Test1234! | SALES |
| owner@test.com | Test1234! | OWNER |
| designer@test.com | Test1234! | DESIGNER |
