"""한국 표준시(KST, UTC+9) 관련 유틸리티.

DB 에는 naive UTC datetime 으로 저장하고,
비즈니스 로직상 "오늘/이번 달" 경계와 화면 표시용 문자열은 KST 기준으로 처리한다.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 KST 시각 (aware datetime)."""
    return datetime.now(KST)


def today_kst() -> date:
    """KST 기준 오늘 날짜."""
    return now_kst().date()


def kst_day_start_utc(kst_date: Optional[date] = None) -> datetime:
    """KST 특정 날짜의 00:00:00 KST 를 naive UTC datetime 으로 반환한다.

    DB 필터 경계값으로 사용: Transaction.created_at >= kst_day_start_utc()
    """
    if kst_date is None:
        kst_date = today_kst()
    kst_midnight = datetime(kst_date.year, kst_date.month, kst_date.day, tzinfo=KST)
    return kst_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def fmt_kst(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S") -> Optional[str]:
    """Naive UTC datetime 을 KST 문자열로 변환한다.

    API 응답에서 datetime 을 사람이 읽을 수 있는 KST 문자열로 내려줄 때 사용.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime(fmt)
