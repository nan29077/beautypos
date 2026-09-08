"""데모/운영 계정의 로그인 ID·비밀번호를 현재 규격으로 맞춘다.

app/seed.py 의 ACCOUNT_SPECS 를 그대로 따르며, 이미 만들어진 DB(로컬 SQLite,
운영 RDS 모두)에 대해 멱등하게 동작한다.

    python -m scripts.set_accounts --dry-run   # 무엇이 바뀌는지만 출력
    python -m scripts.set_accounts             # 실제 반영

동작:
  - 현재 ID 로 계정이 있으면 → 비밀번호만 다시 설정
  - 예전 ID 로만 있으면      → ID 를 현재 ID 로 바꾸고 비밀번호 재설정
  - 둘 다 있으면            → 충돌로 보고 건드리지 않음
  - 둘 다 없으면            → 없음으로 보고(계정 생성은 하지 않음)

비밀번호를 매 배포마다 되돌리지 않으려고 일부러 수동 스크립트로 둔다.
"""
import sys

from app.database import SessionLocal
from app.models.user import User
from app.seed import ACCOUNT_SPECS, pwd_context


def sync_accounts(db, dry_run: bool = False) -> int:
    changed = 0
    for email, legacy_email, password in ACCOUNT_SPECS:
        current = db.query(User).filter(User.email == email).first()
        legacy = db.query(User).filter(User.email == legacy_email).first() if legacy_email else None

        if current and legacy and current.id != legacy.id:
            print(f"   [충돌] {email} 와 {legacy_email} 이 모두 있어 건너뜁니다 "
                  f"(id={current.id}, {legacy.id})")
            continue

        user = current or legacy
        if not user:
            print(f"   [없음] {email} (이전: {legacy_email}) — 시드가 안 된 DB 입니다")
            continue

        renamed = user.email != email
        if not dry_run:
            user.email = email
            user.password_hash = pwd_context.hash(password)
        role = user.role.value if hasattr(user.role, "value") else user.role
        action = f"{legacy_email} → {email}" if renamed else f"{email} 비밀번호 재설정"
        print(f"   [{'예정' if dry_run else '반영'}] {role:8s} {action}")
        changed += 1

    if not dry_run:
        db.commit()
    return changed


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        print("계정 설정을 맞춥니다" + (" (dry-run)" if dry_run else ""))
        changed = sync_accounts(db, dry_run=dry_run)
        print(f"완료: {changed}건")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
