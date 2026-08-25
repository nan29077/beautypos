# ADPAY — 오프라인 PG + 직원별 매출 + 광고/분석/주문 플랫폼

## 프로젝트 개요

ADPAY는 오프라인 매장에 카드 단말기를 배포하고, 단말기에서 발생하는 결제를 관리하는 통합 플랫폼입니다.

### 핵심 기능
- **가맹점별 PG 연동 관리** (씨드페이먼츠/키움페이/토스)
- **결제/정산 관리** — 일 단위 정산 계산
- **직원(디자이너)별 매출 분리** — staff_code 기반 자동 귀속
- **영업관리자 커미션/출금요청** 워크플로우
- **광고 분석** — 플레이스 순위/리뷰 경쟁 비교
- **광고 주문** — 블로그 배포/플레이스 방문 요청 → 관리자 집행
- **랜딩페이지 3페이지** + 소셜 로그인 + 테스트 계정 원클릭 로그인

## 기술 스택
| 분류 | 기술 |
|------|------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic |
| Database | MariaDB (Docker) / SQLite (로컬 개발) |
| Auth | JWT (Access/Refresh), bcrypt, OAuth stub (카카오/네이버/구글) |
| Frontend | HTML5 + Vanilla JS + Bootstrap 5 + Font Awesome |
| Infra | Docker Compose |

## 빠른 시작 (Docker Compose)

```bash
# 1. 클론
git clone <repo-url> && cd adpay

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에서 DATABASE_URL_OVERRIDE 라인 삭제 또는 주석 처리 (MariaDB 사용)

# 3. 실행
docker-compose up --build

# 4. 접속
# - 랜딩: http://localhost:8000/static/landing/index.html
# - 로그인: http://localhost:8000/static/login.html
# - API Docs: http://localhost:8000/docs
```

## 로컬 개발 (SQLite)

```bash
pip install -r requirements.txt

# .env에 아래 추가
DATABASE_URL_OVERRIDE=sqlite:///./adpay.db

python -m app.init_db
uvicorn app.main:app --reload --port 8000
```

## 테스트 계정

| 역할 | 이메일 | 비밀번호 |
|------|--------|----------|
| 최고관리자 | admin@test.com | Test1234! |
| 영업관리자 | sales@test.com | Test1234! |
| 원장님 | owner@test.com | Test1234! |
| 디자이너 | designer@test.com | Test1234! |

로그인 화면 하단 "테스트 계정으로 빠른 로그인" 버튼으로 원클릭 로그인 가능

## 사용자 역할별 기능

### 최고관리자 (admin)
- 가맹점 리스트/생성/수정
- 가맹점별 PG 설정 (MID/SECRET 등록 + 연동 테스트)
- 전체 결제/정산/출금요청 관리
- 광고 주문 전체 리스트/상태 변경/집행 메모
- 광고 Metrics 등록
- 영업배정 관리
- 랜딩 통계 API

### 영업관리자 (sales)
- 담당 가맹점 리스트 및 통계
- 결제/수수료/커미션 확인
- 출금요청 생성/조회

### 원장님 (owner)
- 내 매장 결제/정산 조회
- 직원(디자이너) 관리 (추가/비활성화)
- 직원별 매출 조회 (기간 필터)
- 광고 분석 (우리 매장 vs 경쟁업체 비교)
- 광고 주문 (블로그 배포 / 플레이스 방문)

### 디자이너 (designer)
- 본인 결제내역/매출 합계 (기간 필터)

## API 엔드포인트 목록

### Auth
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/register` | 회원가입 |
| POST | `/api/auth/login` | 이메일 로그인 |
| GET | `/api/auth/oauth/{provider}/start` | OAuth 시작 URL |
| GET | `/api/auth/oauth/{provider}/callback` | OAuth 콜백 |
| POST | `/api/auth/test-login?role=admin\|sales\|owner\|designer` | 테스트 로그인 |
| GET | `/api/me` | 현재 유저 정보 |

### Admin
| Method | Path | 설명 |
|--------|------|------|
| GET/POST | `/api/admin/merchants` | 가맹점 CRUD |
| PUT | `/api/admin/merchants/{id}` | 가맹점 수정 |
| GET | `/api/admin/merchants/{id}/pg-configs` | PG 설정 조회 |
| POST | `/api/admin/merchants/{id}/pg-config` | PG 설정 등록 |
| POST | `/api/admin/merchants/{id}/pg-test` | PG 연동 테스트 |
| GET | `/api/admin/pg-providers` | PG사 목록 |
| GET | `/api/admin/transactions` | 전체 결제 조회 |
| GET | `/api/admin/settlements` | 정산 목록 |
| POST | `/api/admin/settlements/calculate` | 정산 계산 |
| GET | `/api/admin/payout-requests` | 출금요청 목록 |
| POST | `/api/admin/payout-requests/{id}/approve` | 출금 승인 |
| POST | `/api/admin/payout-requests/{id}/reject` | 출금 거절 |
| GET | `/api/admin/ad/orders` | 광고주문 전체 |
| POST | `/api/admin/ad/orders/{id}/status` | 광고주문 상태변경 |
| POST | `/api/admin/ad/metrics` | Metrics 등록 |
| GET | `/api/admin/stats/landing` | 랜딩 통계 |

### Terminal
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/terminal/transactions` | 단말기 결제 인입 (X-Terminal-Key 헤더) |

### Owner
| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/owner/transactions` | 매장 결제 조회 |
| GET/POST | `/api/owner/staff` | 직원 관리 |
| PUT | `/api/owner/staff/{id}` | 직원 수정 |
| GET | `/api/owner/staff/{id}/sales` | 직원별 매출 |
| GET | `/api/owner/ad/analysis` | 광고 분석 |
| POST | `/api/owner/ad/blog-orders` | 블로그 주문 |
| POST | `/api/owner/ad/place-traffic-orders` | 플레이스 주문 |
| GET | `/api/owner/ad/orders` | 내 광고 주문 |

### Sales
| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/sales/merchants` | 담당 가맹점 |
| GET | `/api/sales/merchants/{id}/stats` | 가맹점 통계 |
| POST | `/api/sales/payout-requests` | 출금요청 |
| GET | `/api/sales/payout-requests` | 출금요청 목록 |

### Designer
| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/designer/transactions` | 내 결제 내역 |

## 프로젝트 구조

```
webapp/
├── app/
│   ├── main.py              # FastAPI 앱 엔트리
│   ├── config.py             # 설정 (Pydantic Settings)
│   ├── database.py           # SQLAlchemy 엔진/세션
│   ├── init_db.py            # DB 초기화 + 시드
│   ├── seed.py               # 테스트 데이터 시드
│   ├── auth/
│   │   ├── jwt_handler.py    # JWT 토큰 생성/검증
│   │   └── dependencies.py   # RBAC 의존성
│   ├── api/
│   │   ├── auth_routes.py    # 인증 API
│   │   ├── admin_routes.py   # 관리자 API
│   │   ├── terminal_routes.py # 단말기 API
│   │   ├── owner_routes.py   # 원장 API
│   │   ├── sales_routes.py   # 영업 API
│   │   └── designer_routes.py # 디자이너 API
│   ├── models/               # SQLAlchemy 모델
│   │   ├── user.py, merchant.py, staff.py
│   │   ├── terminal.py, pg.py, transaction.py
│   │   ├── settlement.py, ad.py
│   │   └── __init__.py
│   ├── schemas/
│   │   └── schemas.py        # Pydantic 스키마
│   └── services/
│       ├── encryption.py     # PG SECRET 암호화
│       └── pg_service.py     # PG Provider Mock
├── static/
│   ├── landing/
│   │   ├── index.html        # 랜딩 메인
│   │   ├── features.html     # 기능 소개
│   │   └── pricing.html      # 요금제
│   ├── login.html            # 로그인/회원가입
│   ├── dashboard.html        # 메인 대시보드
│   ├── css/style.css
│   └── js/
│       ├── api.js            # API 헬퍼
│       └── dashboard.js      # SPA 라우팅/렌더링
├── alembic/                  # Alembic 마이그레이션
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── .env.example
└── .gitignore
```

## DB ERD (주요 테이블)

- **users** — 이메일/비밀번호/역할(admin/sales/owner/designer)/OAuth
- **merchants** — 가맹점 (owner_user_id FK)
- **staff** — 직원 (merchant_id, staff_code unique per merchant)
- **terminal_devices** — 단말기 (api_key 인증)
- **pg_providers** — PG사 마스터 (seedpayments/kiwoompay/toss)
- **merchant_pg_configs** — 가맹점별 PG 설정 (MID/SECRET 암호화)
- **transactions** — 결제 (staff_id nullable → 직원/원장 귀속)
- **fee_policies** — 가맹점별 PG 수수료율
- **merchant_sales_assignments** — 영업관리자 배정 + 커미션율
- **settlements** — 정산 (기간별 총매출/수수료/순매출)
- **payout_requests** — 출금요청 (pending → approved/rejected)
- **ad_place_profiles** — 우리 매장 플레이스 정보
- **ad_competitors** — 경쟁업체 플레이스
- **ad_metrics** — 지표 (블로그리뷰수/방문자리뷰수/순위)
- **ad_orders** — 광고주문 (blog/place_traffic)
- **ad_order_blog_details** — 블로그 배포 상세
- **ad_order_place_traffic_details** — 플레이스 방문 상세

## 시드 데이터

- 테스트 계정 4+1개
- 가맹점 1개 (뷰티헤어살롱 강남점)
- 직원 2명 (홍길동 코드1, 이디자 코드2)
- 단말기 1개 (TERM001, API Key: `term-api-key-001`)
- PG Provider 3개
- 샘플 결제 10건 (직원 귀속 포함)
- 샘플 광고 주문 2건 + 7일치 Metrics

## 보안 사항
- PG SECRET은 Fernet 대칭 암호화로 DB 저장
- API 응답 시 SECRET은 마스킹 처리
- JWT Access/Refresh 토큰 기반 인증
- RBAC 데코레이터로 역할별 접근 통제
- 테스트 로그인은 DEV_MODE=true일 때만 허용

## 광고 모듈 참고
- 외부 사이트 자동 스크래핑은 구현하지 않음
- 플레이스 방문·블로그 배포 집행은 제휴 광고 플랫폼 API 연동으로 처리한다 (연동 예정)
- 수치는 관리자/원장이 직접 입력하거나 업로드하는 방식
- 추후 공식 API 연동을 위한 metrics_provider 인터페이스 stub 준비
