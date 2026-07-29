"""
네이버 플레이스 지표 수집 서비스.

- 블로그/방문자 리뷰 수: m.place.naver.com 상세 페이지의 SSR 데이터에서 추출
- 검색 순위: pcmap.place.naver.com 목록 페이지의 Apollo 상태(광고 목록이 분리되어 있음)에서 추출
  (실패 시 m.search.naver.com 모바일 검색 HTML 파싱으로 폴백)

Selenium / Playwright 등 브라우저 드라이버는 사용하지 않는다. httpx 비동기 요청만 사용하며,
여러 대상은 asyncio.gather 로 병렬 조회한다.
"""
import asyncio
import json
import logging
import re
from datetime import date as date_cls, datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urlsplit, parse_qs

import httpx

logger = logging.getLogger(__name__)

# ─── 상수 ────────────────────────────────────────────────────

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
PC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 8.0

# 순위 수집 범위. pcmap SSR 은 1회 최대 100건(display 상한)이므로
# 100건 단위로 페이지네이션해 200위까지 확인한다.
MAX_RANK_SCAN = 200
RANK_PAGE_SIZE = 100
RANK_OUT_OF_RANGE = MAX_RANK_SCAN + 1  # 200위 밖(=201)을 뜻하는 센티넬

# 네이버는 동시 요청이 많으면 429(Too Many Requests)를 반환한다.
# 병렬 처리로 속도를 확보하되 차단되지 않도록 동시 요청 수를 제한하고 재시도한다.
MAX_CONCURRENCY = 3
MAX_ATTEMPTS = 3
RETRY_BACKOFF = (0.8, 2.0)  # 재시도 전 대기 시간(초)

# 짧은 간격의 반복 수집은 네이버 요청 한도를 소진시키므로 강제 재수집을 제한한다.
FORCE_REFRESH_COOLDOWN_SECONDS = 60

PLACE_DETAIL_URL = "https://m.place.naver.com/place/{place_id}/home"
PCMAP_LIST_URL = "https://pcmap.place.naver.com/place/list"
PCMAP_GRAPHQL_URL = "https://pcmap-api.place.naver.com/place/graphql"
MOBILE_SEARCH_URL = "https://m.search.naver.com/search.naver"

# GraphQL 인라인 리터럴로 넣을 때 따옴표를 붙이면 안 되는 enum 키
_GQL_ENUM_KEYS = {"sortingOrder"}

_RE_VISITOR = re.compile(r'"visitorReviewsTotal"\s*:\s*(\d+)')
_RE_BLOG = re.compile(r'"cafeBlogReviewsTotal"\s*:\s*(\d+)')
_RE_NAME = re.compile(r'"name"\s*:\s*"((?:[^"\\]|\\.){1,80})"')
_RE_PLACE_ID_PATH = re.compile(r"/(?:place|entry|restaurant|hairshop|beauty|hospital|cafe)/(\d{6,})")
_RE_PLACE_ID_ANY = re.compile(r"/(\d{6,})(?:[/?#]|$)")
_RE_AD_DOC_ID = re.compile(r"_nad-")


def _headers(mobile: bool = True, referer: str = "https://m.search.naver.com/") -> Dict[str, str]:
    """네이버가 봇으로 판단하지 않도록 일반 브라우저와 동일한 헤더를 구성한다."""
    return {
        "User-Agent": MOBILE_UA if mobile else PC_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": referer,
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
    }


def build_client() -> httpx.AsyncClient:
    """수집용 공용 AsyncClient (연결 재사용으로 다건 조회 시 지연을 줄인다)."""
    return httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=MAX_CONCURRENCY,
            max_keepalive_connections=MAX_CONCURRENCY,
        ),
    )


async def _get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> Optional[httpx.Response]:
    """동시 요청 수를 제한하고 429/5xx 응답은 백오프 후 재시도한다."""
    for attempt in range(MAX_ATTEMPTS):
        if semaphore is not None:
            async with semaphore:
                response = await _get_once(client, url, params, headers)
        else:
            response = await _get_once(client, url, params, headers)

        if response is None:
            return None
        if response.status_code == 200:
            return response
        if response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS - 1:
            wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            logger.info(
                "네이버 요청이 제한되어 %.1f초 후 재시도합니다 (HTTP %s, %s)",
                wait, response.status_code, url,
            )
            await asyncio.sleep(wait)
            continue
        return response
    return None


async def _get_once(client, url, params, headers) -> Optional[httpx.Response]:
    try:
        return await client.get(url, params=params, headers=headers)
    except Exception as exc:  # noqa: BLE001 — 네트워크 오류는 None 으로 흡수
        logger.warning("네이버 요청 실패 (%s): %s", url, exc)
        return None


# ─── place_id 추출 ───────────────────────────────────────────

def extract_place_id(url: str) -> Optional[str]:
    """네이버 플레이스 URL에서 place_id를 추출한다. 실패하면 None."""
    raw = (url or "").strip()
    if not raw:
        return None

    # 순수 숫자만 입력한 경우 그대로 place_id 로 취급
    if raw.isdigit() and len(raw) >= 6:
        return raw

    try:
        parts = urlsplit(raw if "://" in raw else f"https://{raw}")
    except ValueError:
        return None

    # 쿼리스트링 형태 (?id= / ?placeId= / ?entry= 등)
    query = parse_qs(parts.query or "")
    for key in ("id", "placeId", "place_id", "code"):
        for value in query.get(key, []):
            if value.isdigit() and len(value) >= 6:
                return value

    path = parts.path or ""
    match = _RE_PLACE_ID_PATH.search(path) or _RE_PLACE_ID_ANY.search(path)
    if match:
        return match.group(1)
    return None


async def resolve_place_id(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> Optional[str]:
    """단축 URL(naver.me 등)까지 고려해 place_id를 확보한다."""
    direct = extract_place_id(url)
    if direct:
        return direct
    if not url or "naver.me" not in url:
        return None

    own_client = client is None
    client = client or build_client()
    try:
        response = await _get(client, url, headers=_headers(), semaphore=semaphore)
        return extract_place_id(str(response.url)) if response is not None else None
    except Exception as exc:  # noqa: BLE001 — 수집 실패는 None 으로 흡수
        logger.warning("네이버 단축 URL 해석 실패 (%s): %s", url, exc)
        return None
    finally:
        if own_client:
            await client.aclose()


# ─── 리뷰 수 조회 ────────────────────────────────────────────

async def fetch_place_reviews(
    place_id: str,
    client: Optional[httpx.AsyncClient] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> Optional[Dict[str, Any]]:
    """블로그 리뷰 수 + 방문자 리뷰 수를 조회한다. 실패하면 None."""
    if not place_id:
        return None

    own_client = client is None
    client = client or build_client()
    try:
        response = await _get(
            client,
            PLACE_DETAIL_URL.format(place_id=place_id),
            headers=_headers(referer="https://m.place.naver.com/"),
            semaphore=semaphore,
        )
        if response is None or response.status_code != 200:
            logger.warning(
                "플레이스 상세 조회 실패 (%s): HTTP %s",
                place_id, response.status_code if response else "연결 실패",
            )
            return None

        body = response.text
        visitor = _RE_VISITOR.search(body)
        blog = _RE_BLOG.search(body)
        if not visitor and not blog:
            # 존재하지 않는 place_id 이거나 응답 구조가 변경된 경우
            logger.warning("플레이스 상세에서 리뷰 지표를 찾지 못했습니다 (%s)", place_id)
            return None

        name = _RE_NAME.search(body)
        return {
            "place_id": place_id,
            "blog_count": int(blog.group(1)) if blog else 0,
            "visitor_count": int(visitor.group(1)) if visitor else 0,
            "name": _unescape_json_str(name.group(1)) if name else None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("플레이스 리뷰 수집 실패 (%s): %s", place_id, exc)
        return None
    finally:
        if own_client:
            await client.aclose()


def _unescape_json_str(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except Exception:  # noqa: BLE001
        return value


# ─── 검색 순위 조회 ──────────────────────────────────────────

def _extract_apollo_state(html: str) -> Dict[str, Any]:
    """SSR 페이지에 삽입된 window.__APOLLO_STATE__ JSON을 잘라낸다."""
    marker = html.find("__APOLLO_STATE__")
    if marker == -1:
        return {}
    start = html.find("{", marker)
    if start == -1:
        return {}

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(html)):
        char = html[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:index + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def _find_ref_lists(node: Any, depth: int = 0) -> List[List[Any]]:
    """중첩된 Apollo 응답에서 `items: [{__ref: ...}]` 형태의 목록을 모두 찾는다.

    업종에 따라 목록 위치가 다르다.
    - 미용실: hairshopList(...).items
    - 음식점/카페: placeList(...).businesses.items
    - 병원: hospitals(...).items
    """
    found: List[List[Any]] = []
    if depth > 3 or not isinstance(node, dict):
        return found
    items = node.get("items")
    if isinstance(items, list) and items and all(
        isinstance(i, dict) and "__ref" in i for i in items
    ):
        found.append(items)
    for key, value in node.items():
        if key != "items" and isinstance(value, dict):
            found.extend(_find_ref_lists(value, depth + 1))
    return found


def _find_items_path(node: Any, depth: int = 0, path: tuple = ()) -> Optional[tuple]:
    """`items` 목록이 놓인 경로를 찾는다 (음식점/카페는 `businesses` 아래에 있다)."""
    if depth > 3 or not isinstance(node, dict):
        return None
    items = node.get("items")
    if isinstance(items, list) and items and all(
        isinstance(i, dict) and "__ref" in i for i in items
    ):
        return path
    for key, value in node.items():
        if key != "items" and isinstance(value, dict):
            found = _find_items_path(value, depth + 1, path + (key,))
            if found is not None:
                return found
    return None


def _gql_literal(value: Any, key: Optional[str] = None) -> str:
    """JSON 값을 GraphQL 인라인 리터럴로 변환한다.

    변수 선언을 쓰지 않으므로 업종별 input 타입명(BeautyListInput 등)을 알 필요가 없다.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        # enum 값은 따옴표 없이 그대로 넣어야 한다.
        return value if key in _GQL_ENUM_KEYS else json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_gql_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}:{_gql_literal(v, k)}" for k, v in value.items()) + "}"
    return "null"


def _entries_to_ranking(entries: List[Dict[str, Any]], ranking: List[Dict[str, Any]]) -> None:
    """조회 결과를 순위 목록에 이어붙인다 (새로오픈 제외, 중복 제거)."""
    seen = {r["place_id"] for r in ranking}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("newOpening"):
            continue  # 새로오픈 배지 노출 업체는 순위에서 제외
        place_id = str(entry.get("id") or "").strip()
        if not place_id or place_id in seen:
            continue  # 페이지 경계에서 중복이 생길 수 있어 걸러낸다
        seen.add(place_id)
        ranking.append({
            "place_id": place_id,
            "name": entry.get("name"),
            "rank": len(ranking) + 1,
        })
        if len(ranking) >= MAX_RANK_SCAN:
            return


def _next_page_start(raw_consumed: int) -> int:
    """네이버는 새로오픈 포함 '원본 개수' 기준으로 페이징하므로 그 값으로 start를 계산한다."""
    return raw_consumed + 1


def _parse_pcmap_page(html: str) -> Dict[str, Any]:
    """pcmap 1페이지에서 순위 목록과 다음 페이지 조회용 컨텍스트를 함께 뽑아낸다.

    Apollo 상태에서 광고는 `adBusinesses` 키로 분리되어 있으므로 해당 키를 건너뛰고,
    남은 목록 중 가장 긴 것을 순위 목록으로 사용한다.
    """
    state = _extract_apollo_state(html)
    root = state.get("ROOT_QUERY") or {}

    best_key: Optional[str] = None
    best_value: Optional[Dict[str, Any]] = None
    best_items: List[Any] = []
    for key, value in root.items():
        if key.startswith("adBusinesses") or not isinstance(value, dict):
            continue  # 광고 목록은 순위에서 제외
        for candidate in _find_ref_lists(value):
            if len(candidate) > len(best_items):
                best_key, best_value, best_items = key, value, candidate

    ranking: List[Dict[str, Any]] = []
    entries = []
    for item in best_items:
        ref = item.get("__ref") if isinstance(item, dict) else item
        entry = state.get(ref) if isinstance(ref, str) else None
        if isinstance(entry, dict):
            entries.append(entry)
    _entries_to_ranking(entries, ranking)
    raw_consumed = len(entries)

    # 다음 페이지 요청에 필요한 정보(필드명 / input / items 경로)를 그대로 재사용한다.
    context: Optional[Dict[str, Any]] = None
    if best_key and "(" in best_key:
        field = best_key.split("(")[0]
        try:
            args = json.loads(best_key[len(field) + 1:-1])
            gql_input = args.get("input")
            if isinstance(gql_input, dict):
                context = {
                    "field": field,
                    "input": gql_input,
                    "path": _find_items_path(best_value) or (),
                }
        except (json.JSONDecodeError, ValueError):
            context = None

    return {"ranking": ranking, "context": context, "raw_consumed": raw_consumed}


def _parse_pcmap_ranking(html: str) -> List[Dict[str, Any]]:
    """pcmap 목록 페이지에서 광고·새로오픈을 제외한 순위 목록을 만든다."""
    return _parse_pcmap_page(html)["ranking"]


async def _fetch_rank_page(
    client: httpx.AsyncClient,
    context: Dict[str, Any],
    start: int,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> List[Dict[str, Any]]:
    """pcmap GraphQL 로 2페이지 이후(101위~)를 조회한다. 실패하면 빈 목록."""
    gql_input = dict(context["input"])
    gql_input["start"] = start
    gql_input["display"] = RANK_PAGE_SIZE

    selection = "items { id name newOpening }"
    for part in reversed(context["path"]):
        selection = "%s { %s }" % (part, selection)
    query = "query { result: %s(input: %s) { %s } }" % (
        context["field"], _gql_literal(gql_input), selection,
    )

    headers = {
        **_headers(mobile=False, referer="https://pcmap.place.naver.com/"),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://pcmap.place.naver.com",
    }
    try:
        if semaphore is not None:
            async with semaphore:
                response = await client.post(PCMAP_GRAPHQL_URL, json={"query": query}, headers=headers)
        else:
            response = await client.post(PCMAP_GRAPHQL_URL, json={"query": query}, headers=headers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("순위 다음 페이지 조회 실패 (start=%s): %s", start, exc)
        return []

    if response.status_code != 200:
        logger.warning("순위 다음 페이지 조회 실패 (start=%s): HTTP %s", start, response.status_code)
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    if payload.get("errors"):
        logger.warning("순위 다음 페이지 GraphQL 오류 (start=%s): %s", start, payload["errors"][:1])
        return []

    node = (payload.get("data") or {}).get("result")
    for part in context["path"]:
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    if not isinstance(node, dict):
        return []
    items = node.get("items")
    return items if isinstance(items, list) else []


def _parse_mobile_search_ranking(html: str) -> List[Dict[str, Any]]:
    """모바일 검색 HTML 폴백 파서 — 광고/새로오픈 항목을 제외한다."""
    try:
        from bs4 import BeautifulSoup  # 지연 임포트: 폴백 경로에서만 필요
    except ImportError:
        logger.warning("beautifulsoup4 미설치로 모바일 검색 폴백을 사용할 수 없습니다")
        return []

    soup = BeautifulSoup(html, "html.parser")
    ranking: List[Dict[str, Any]] = []
    for li in soup.find_all("li"):
        doc_id = next((v for k, v in li.attrs.items() if k.endswith("-doc-id")), None)
        if not doc_id:
            continue
        markup = str(li)
        text = li.get_text(" ", strip=True)
        # 광고 판별: 광고 문서ID(_nad-), 광고 라벨 아이콘, '광고' 뱃지 텍스트
        if _RE_AD_DOC_ID.search(doc_id) or "place_ad_label" in markup:
            continue
        if "새로오픈" in text or "새로 오픈" in text:
            continue
        place_id = str(doc_id).split("_")[0].strip()
        if not place_id.isdigit():
            continue
        if any(r["place_id"] == place_id for r in ranking):
            continue
        ranking.append({
            "place_id": place_id,
            "name": text[:40] or None,
            "rank": len(ranking) + 1,
        })
        if len(ranking) >= MAX_RANK_SCAN:
            break
    return ranking


async def fetch_rank_list(
    keyword: str,
    client: Optional[httpx.AsyncClient] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
    wanted_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """키워드 1건에 대한 순위 목록(광고·새로오픈 제외)을 최대 200위까지 조회한다.

    `wanted_ids` 를 주면 찾는 대상이 모두 나온 시점에 조회를 멈춘다.
    대부분의 매장이 100위 안에 있으므로 보통 1회 요청으로 끝나 속도가 유지된다.
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return []

    own_client = client is None
    client = client or build_client()
    try:
        response = await _get(
            client,
            PCMAP_LIST_URL,
            # SSR 은 display 최대 100건까지 허용한다.
            params={"query": keyword, "display": RANK_PAGE_SIZE},
            headers=_headers(mobile=False, referer="https://pcmap.place.naver.com/"),
            semaphore=semaphore,
        )
        if response is not None and response.status_code == 200:
            parsed = _parse_pcmap_page(response.text)
            ranking = parsed["ranking"]
            context = parsed["context"]
            raw_consumed = parsed["raw_consumed"]
            if ranking:
                # 찾는 대상이 1페이지에 모두 있으면 추가 요청 없이 종료한다.
                while (
                    context
                    and len(ranking) < MAX_RANK_SCAN
                    and not _all_found(ranking, wanted_ids)
                ):
                    entries = await _fetch_rank_page(
                        client, context,
                        start=_next_page_start(raw_consumed), semaphore=semaphore,
                    )
                    if not entries:
                        break
                    raw_consumed += len(entries)
                    before = len(ranking)
                    _entries_to_ranking(entries, ranking)
                    if len(ranking) == before:
                        break  # 더 이상 새로운 항목이 없으면 중단
                return ranking[:MAX_RANK_SCAN]
        logger.warning("pcmap 순위 조회 실패 (%s), 모바일 검색으로 폴백합니다", keyword)

        # 폴백: 모바일 검색 결과 HTML 파싱
        response = await _get(
            client,
            MOBILE_SEARCH_URL,
            params={"where": "m", "query": keyword},
            headers=_headers(),
            semaphore=semaphore,
        )
        if response is None or response.status_code != 200:
            logger.warning("모바일 검색 조회 실패 (%s)", keyword)
            return []
        return _parse_mobile_search_ranking(response.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("순위 수집 실패 (%s): %s", keyword, exc)
        return []
    finally:
        if own_client:
            await client.aclose()


def _all_found(ranking: List[Dict[str, Any]], wanted_ids: Optional[set]) -> bool:
    """찾는 대상이 모두 순위 목록에 나왔는지 확인한다."""
    if not wanted_ids:
        return False  # 대상 지정이 없으면 200위까지 모두 수집
    found = {r["place_id"] for r in ranking}
    return all(str(pid) in found for pid in wanted_ids)


def _rank_of(ranking: List[Dict[str, Any]], place_id: str) -> Optional[int]:
    """순위 목록에서 place_id 의 순위를 찾는다.

    - 목록에 있으면 해당 순위
    - 목록은 받았지만 없으면 RANK_OUT_OF_RANGE(201) = '200위 밖'
    - 목록 자체를 못 받았으면 None = '확인 불가'
    """
    if not ranking:
        return None
    for entry in ranking:
        if entry["place_id"] == str(place_id):
            return entry["rank"]
    return RANK_OUT_OF_RANGE


async def fetch_place_rank(
    keyword: str,
    place_id: str,
    client: Optional[httpx.AsyncClient] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> Optional[int]:
    """검색 순위를 반환한다 (광고·새로오픈 제외, 최대 200위).

    200위 안에 없으면 RANK_OUT_OF_RANGE(201), 조회 자체가 실패하면 None.
    """
    if not place_id:
        return None
    ranking = await fetch_rank_list(
        keyword, client=client, semaphore=semaphore, wanted_ids={str(place_id)},
    )
    return _rank_of(ranking, place_id)


# ─── 가맹점 단위 병렬 수집 ───────────────────────────────────

async def collect_targets(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """대상 목록(place_url / place_id / keyword)의 리뷰 수와 순위를 병렬 수집한다.

    같은 키워드는 순위 목록을 1회만 조회해 재사용한다.
    """
    if not targets:
        return []

    # 네이버 429 차단을 피하기 위해 동시 요청 수를 제한한다.
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async with build_client() as client:
        # 1) place_id 확보 (단축 URL 포함)
        resolved = await asyncio.gather(*[
            _resolve_target(target, client, semaphore) for target in targets
        ])

        # 2) 키워드별 순위 목록 1회 조회 + 대상별 리뷰 수 조회를 동시에 실행
        keywords = sorted({
            (t.get("keyword") or "").strip()
            for t in resolved if (t.get("keyword") or "").strip()
        })
        review_ids = [t["place_id"] for t in resolved if t.get("place_id")]

        # 키워드별로 '찾아야 할 place_id' 를 넘겨, 모두 찾으면 다음 페이지를 조회하지 않는다.
        wanted_by_keyword = {k: set() for k in keywords}
        for t in resolved:
            kw = (t.get("keyword") or "").strip()
            if kw and t.get("place_id"):
                wanted_by_keyword[kw].add(str(t["place_id"]))

        rank_task = asyncio.gather(*[
            fetch_rank_list(
                k, client=client, semaphore=semaphore, wanted_ids=wanted_by_keyword.get(k),
            )
            for k in keywords
        ])
        review_task = asyncio.gather(*[
            fetch_place_reviews(pid, client=client, semaphore=semaphore) for pid in review_ids
        ])
        rank_lists, review_results = await asyncio.gather(rank_task, review_task)

    rank_by_keyword = dict(zip(keywords, rank_lists))
    reviews_by_id: Dict[str, Any] = {}
    for pid, result in zip(review_ids, review_results):
        reviews_by_id[pid] = result

    collected: List[Dict[str, Any]] = []
    for target in resolved:
        place_id = target.get("place_id")
        keyword = (target.get("keyword") or "").strip() or None
        reviews = reviews_by_id.get(place_id) if place_id else None

        # 200위 안에 없으면 RANK_OUT_OF_RANGE(201), 조회 실패면 None
        rank = None
        if place_id and keyword:
            rank = _rank_of(rank_by_keyword.get(keyword, []), place_id)

        # 리뷰 조회에 실패한 채로 순위 목록에도 없다면 존재하지 않는 플레이스일 가능성이 높다.
        # 이 경우를 '200위 밖'으로 단정하지 않고 수집 실패로 남긴다.
        if reviews is None and rank == RANK_OUT_OF_RANGE:
            rank = None
        found = bool(reviews) or rank is not None

        collected.append({
            **target,
            "place_id": place_id,
            "keyword": keyword,
            "blog_count": reviews["blog_count"] if reviews else None,
            "visitor_count": reviews["visitor_count"] if reviews else None,
            "place_name": reviews.get("name") if reviews else None,
            "rank": rank,
            "ok": found,
            "error": None if found else _failure_reason(place_id, keyword),
        })
    return collected


def _failure_reason(place_id: Optional[str], keyword: Optional[str]) -> str:
    if not place_id:
        return "플레이스 URL에서 place_id를 추출하지 못했습니다"
    if not keyword:
        return "검색어가 없어 순위를 조회하지 못했고 리뷰 수집에도 실패했습니다"
    return "네이버 응답에서 지표를 확인하지 못했습니다"


async def _resolve_target(
    target: Dict[str, Any],
    client: httpx.AsyncClient,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> Dict[str, Any]:
    place_id = (target.get("place_id") or "").strip() or None
    if not place_id:
        place_id = await resolve_place_id(
            target.get("place_url") or "", client=client, semaphore=semaphore
        )
    return {**target, "place_id": place_id}


async def fetch_all_for_merchant(
    merchant_id: int,
    db=None,
    force: bool = False,
) -> Dict[str, Any]:
    """가맹점의 모든 플레이스(우리 매장 + 경쟁업체)를 병렬 수집하고 DB에 저장한다.

    같은 날 이미 수집된 대상은 기본적으로 재조회하지 않는다(force=True 로 강제 갱신).
    """
    # 지연 임포트로 순환 참조를 피한다.
    from app.database import SessionLocal
    from app.models.ad import AdPlaceProfile, AdCompetitor, AdMetric, PlaceMetricSnapshot

    own_session = db is None
    db = db or SessionLocal()
    started = datetime.utcnow()
    today = started.date()

    try:
        profiles = db.query(AdPlaceProfile).filter(
            AdPlaceProfile.merchant_id == merchant_id
        ).all()
        competitors = db.query(AdCompetitor).filter(
            AdCompetitor.merchant_id == merchant_id
        ).all()

        # 경쟁업체는 자체 검색어가 없으므로 우리 매장의 공통 검색어를 사용한다.
        primary_keyword = next((p.analysis_keyword for p in profiles if p.analysis_keyword), None)

        targets: List[Dict[str, Any]] = []
        for profile in profiles:
            if not profile.place_url:
                continue
            targets.append({
                "kind": "my",
                "label": profile.nickname or profile.place_url,
                "place_url": profile.place_url,
                "place_id": profile.place_id,
                "keyword": profile.analysis_keyword or primary_keyword,
            })
        for competitor in competitors:
            targets.append({
                "kind": "competitor",
                "label": competitor.memo or competitor.competitor_place_url,
                "place_url": competitor.competitor_place_url,
                "place_id": None,
                "keyword": primary_keyword,
            })

        if not targets:
            return {
                "collected": 0, "skipped": 0, "failed": 0, "results": [],
                "elapsed_seconds": 0.0, "keyword": primary_keyword,
                "message": "등록된 플레이스가 없습니다",
            }

        # 캐시: 오늘 이미 저장된 대상은 재조회하지 않는다.
        skipped: List[Dict[str, Any]] = []
        pending: List[Dict[str, Any]] = []
        if force:
            pending = targets
        else:
            cached_urls = {
                row.place_url for row in db.query(AdMetric.place_url).filter(
                    AdMetric.merchant_id == merchant_id,
                    AdMetric.date == today,
                    AdMetric.source == "api",
                ).all()
            }
            for target in targets:
                if target["place_url"] in cached_urls:
                    skipped.append({**target, "cached": True})
                else:
                    pending.append(target)

        results = await collect_targets(pending) if pending else []

        saved = 0
        failed = 0
        for result in results:
            if not result["ok"]:
                failed += 1
                continue
            _upsert_metrics(db, merchant_id, result, today, AdMetric, PlaceMetricSnapshot)
            _sync_profile_place_id(db, merchant_id, result, AdPlaceProfile)
            saved += 1

        db.commit()
        elapsed = (datetime.utcnow() - started).total_seconds()
        return {
            "collected": saved,
            "skipped": len(skipped),
            "failed": failed,
            "elapsed_seconds": round(elapsed, 2),
            "keyword": primary_keyword,
            "collected_at": started.isoformat(),
            "results": [{
                "kind": r["kind"], "label": r["label"], "place_url": r["place_url"],
                "place_id": r["place_id"], "place_name": r["place_name"],
                "blog_count": r["blog_count"], "visitor_count": r["visitor_count"],
                "rank": r["rank"], "ok": r["ok"], "error": r["error"],
            } for r in results] + [{
                "kind": s["kind"], "label": s["label"], "place_url": s["place_url"],
                "place_id": s.get("place_id"), "place_name": None,
                "blog_count": None, "visitor_count": None, "rank": None,
                "ok": True, "error": None, "cached": True,
            } for s in skipped],
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


def _upsert_metrics(db, merchant_id, result, today: date_cls, AdMetric, PlaceMetricSnapshot) -> None:
    """당일 스냅샷과 기존 AdMetric 을 멱등하게 갱신한다."""
    metric = db.query(AdMetric).filter(
        AdMetric.merchant_id == merchant_id,
        AdMetric.place_url == result["place_url"],
        AdMetric.date == today,
    ).first()
    if metric is None:
        metric = AdMetric(
            merchant_id=merchant_id,
            place_url=result["place_url"],
            date=today,
        )
        db.add(metric)
    metric.blog_review_count = result["blog_count"] or 0
    metric.visitor_review_count = result["visitor_count"] or 0
    metric.place_rank = result["rank"]
    metric.search_keyword = result["keyword"]
    metric.source = "api"

    if not result.get("place_id"):
        return

    snapshot = db.query(PlaceMetricSnapshot).filter(
        PlaceMetricSnapshot.merchant_id == merchant_id,
        PlaceMetricSnapshot.place_id == result["place_id"],
        PlaceMetricSnapshot.date == today,
    ).first()
    if snapshot is None:
        snapshot = PlaceMetricSnapshot(
            merchant_id=merchant_id,
            place_id=result["place_id"],
            date=today,
        )
        db.add(snapshot)
    snapshot.place_url = result["place_url"]
    snapshot.place_name = result["place_name"]
    snapshot.kind = result["kind"]
    snapshot.blog_count = result["blog_count"]
    snapshot.visitor_count = result["visitor_count"]
    snapshot.rank = result["rank"]
    snapshot.keyword = result["keyword"]
    snapshot.collected_at = datetime.utcnow()


def _sync_profile_place_id(db, merchant_id, result, AdPlaceProfile) -> None:
    """URL 에서 추출한 place_id 를 프로필에 보관해 다음 수집을 빠르게 한다."""
    if result["kind"] != "my" or not result.get("place_id"):
        return
    profile = db.query(AdPlaceProfile).filter(
        AdPlaceProfile.merchant_id == merchant_id,
        AdPlaceProfile.place_url == result["place_url"],
    ).first()
    if profile is not None and not profile.place_id:
        profile.place_id = result["place_id"]
