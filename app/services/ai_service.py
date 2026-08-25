"""
OpenAI API 키 관리 및 AI 마케팅 추천 서비스.

키는 PG 시크릿과 동일하게 Fernet 으로 암호화해 SystemConfig 에 저장한다.
키가 등록돼 있으면 AI 추천을, 없으면 기존 규칙 기반 문구를 사용한다.
"""
import logging
from typing import Optional

import httpx
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models.system_config import SystemConfig, OPENAI_API_KEY
from app.services.encryption import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)

OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
CONNECTION_TIMEOUT = 10.0


def mask_api_key(plain: str) -> str:
    """API 키를 'sk-...••••••••abcd' 형태로 마스킹한다."""
    if not plain:
        return ""
    prefix = plain[:3] if plain.startswith("sk-") else plain[:2]
    tail = plain[-4:] if len(plain) > 8 else ""
    return f"{prefix}...{'•' * 8}{tail}"


def get_api_key(db: Session) -> Optional[str]:
    """저장된 OpenAI API 키를 복호화해 반환한다. 없으면 None."""
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == OPENAI_API_KEY).first()
    if not cfg or not cfg.config_value:
        return None
    try:
        return decrypt_value(cfg.config_value)
    except Exception as exc:  # noqa: BLE001 — 키 손상/암호화 키 변경 시
        logger.warning("OpenAI API 키 복호화 실패: %s", exc)
        return None


def save_api_key(db: Session, plain: str) -> None:
    """API 키를 암호화해 저장한다."""
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == OPENAI_API_KEY).first()
    if not cfg:
        cfg = SystemConfig(
            config_key=OPENAI_API_KEY,
            description="OpenAI API 키 (AI 마케팅 추천용, Fernet 암호화 저장)",
        )
        db.add(cfg)
    cfg.config_value = encrypt_value(plain)
    cfg.is_enabled = True
    db.commit()


def delete_api_key(db: Session) -> bool:
    """저장된 API 키를 제거한다. 삭제된 경우 True."""
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == OPENAI_API_KEY).first()
    if not cfg or not cfg.config_value:
        return False
    cfg.config_value = None
    cfg.is_enabled = False
    db.commit()
    return True


def is_configured(db: Session) -> bool:
    return get_api_key(db) is not None


async def test_connection(api_key: str) -> dict:
    """OpenAI API 에 실제로 요청해 키가 유효한지 확인한다."""
    if not api_key:
        return {"ok": False, "detail": "등록된 API 키가 없습니다."}
    try:
        async with httpx.AsyncClient(timeout=CONNECTION_TIMEOUT) as client:
            response = await client.get(
                OPENAI_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.TimeoutException:
        return {"ok": False, "detail": "OpenAI 응답이 지연되어 연결을 확인하지 못했습니다."}
    except Exception as exc:  # noqa: BLE001 — 네트워크 오류는 실패로 처리
        logger.warning("OpenAI 연결 테스트 실패: %s", exc)
        return {"ok": False, "detail": "OpenAI 서버에 연결하지 못했습니다. 네트워크를 확인해주세요."}

    if response.status_code == 200:
        try:
            count = len(response.json().get("data", []))
        except Exception:  # noqa: BLE001
            count = 0
        return {"ok": True, "detail": f"연결에 성공했습니다. (사용 가능한 모델 {count}개)"}
    if response.status_code == 401:
        return {"ok": False, "detail": "API 키가 올바르지 않습니다. 키를 다시 확인해주세요."}
    if response.status_code == 429:
        return {"ok": False, "detail": "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."}
    return {"ok": False, "detail": f"OpenAI 응답 오류입니다. (HTTP {response.status_code})"}


async def generate_ad_recommendation(db: Session, context: dict) -> Optional[str]:
    """AI 마케팅 추천 문구를 생성한다.

    키가 없으면 None 을 돌려주고, 호출부는 기존 규칙 기반 문구를 사용한다.
    """
    # 동기 DB 조회 — async 함수 안이라 스레드풀로 넘긴다.
    api_key = await run_in_threadpool(get_api_key, db)
    if not api_key:
        return None

    # TODO: OpenAI Chat Completions 호출로 교체한다.
    #   context 에는 우리 매장/경쟁업체의 순위·리뷰 지표가 담겨 있으므로
    #   이를 프롬프트로 만들어 원장님 눈높이의 실행 제안을 받아온다.
    #   예)
    #   async with httpx.AsyncClient(timeout=30) as client:
    #       r = await client.post(
    #           "https://api.openai.com/v1/chat/completions",
    #           headers={"Authorization": f"Bearer {api_key}"},
    #           json={"model": "gpt-4o-mini", "messages": [...]},
    #       )
    #       return r.json()["choices"][0]["message"]["content"]
    logger.info("AI 추천 요청 (미구현) — 대상 %s건", len(context.get("competitors", [])))
    return None
