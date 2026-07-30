"""정적 파일 캐시 버스팅 (cache busting).

배포 후에도 브라우저가 예전 CSS/JS 를 계속 쓰는 문제를 막는다.
HTML 안의 **로컬** 정적 파일 링크에 `?v=<파일 내용 해시>` 를 자동으로 붙이므로
파일이 바뀌면 URL 이 바뀌고, 브라우저는 새 파일을 내려받는다.
수동으로 버전을 올릴 필요가 없다.

이 프로젝트는 Jinja2 템플릿을 쓰지 않고 StaticFiles 로 HTML 을 그대로 서빙하므로,
`StaticFiles.file_response()` 를 감싸서 응답 시점에 HTML 본문을 다시 쓰는 방식을 쓴다.
(HTML 파일 자체는 수정하지 않는다.)

Cache-Control:
    HTML                → no-cache. 항상 재검증해서 최신 링크(=최신 해시)를 받게 한다.
    ?v= 붙은 정적 파일  → 1년 immutable. 내용이 바뀌면 URL 이 바뀌므로 안전하다.
    ?v= 없는 정적 파일  → StaticFiles 기본 동작 유지 (ETag/Last-Modified 재검증).

CDN(https://…), 프로토콜 상대(//…), data: URL 은 건드리지 않는다.
"""
import hashlib
import os
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# 버전 파라미터를 붙일 확장자
VERSIONED_SUFFIXES = (".css", ".js")

# 버전 파라미터 이름
VERSION_PARAM = "v"

# 내용 해시 길이 (MD5 앞 10자 — 충돌 확률 무시 가능하고 URL 이 짧다)
HASH_LENGTH = 10

HTML_CACHE_CONTROL = "no-cache, must-revalidate"
VERSIONED_CACHE_CONTROL = "public, max-age=31536000, immutable"

# href="..." / src="..." 추출 (따옴표 종류 무관)
_ATTR_RE = re.compile(
    r"""(?P<attr>\b(?:href|src)\s*=\s*)(?P<quote>["'])(?P<url>[^"']*)(?P=quote)""",
    re.IGNORECASE,
)

# 버전을 붙이지 않는 URL 접두사 (외부 리소스 등)
_SKIP_PREFIXES = ("http://", "https://", "//", "data:", "mailto:", "tel:", "#", "javascript:")


def compute_file_version(path: str) -> str:
    """파일 내용의 MD5 앞 HASH_LENGTH 자를 반환한다.

    읽기에 실패하면 수정 시각(mtime)을 대신 쓴다. 캐시 버스팅 용도이므로
    암호학적 강도는 필요하지 않다.
    """
    try:
        digest = hashlib.md5()  # noqa: S324 - 캐시 버스팅용, 보안 용도 아님
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()[:HASH_LENGTH]
    except OSError:
        try:
            return str(int(os.path.getmtime(path)))
        except OSError:
            return "0"


class AssetVersions:
    """정적 파일별 버전 문자열을 보관한다.

    키는 static 디렉터리 기준 상대 URL 경로 (예: "css/style.css").
    dev_mode 면 조회할 때마다 mtime/size 를 확인해 바뀐 파일의 해시를 다시 계산하므로
    서버를 재시작하지 않아도 최신 버전이 반영된다.
    """

    def __init__(self, directory: str, dev_mode: bool = False):
        self.directory = directory
        self.dev_mode = dev_mode
        # key -> (version, mtime_ns, size)
        self._entries: dict[str, tuple[str, int, int]] = {}
        # 버전이 하나라도 바뀌면 증가 — HTML 재작성 캐시 무효화에 사용
        self.revision = 0

    # ── 내부 유틸 ────────────────────────────────────────────
    def _full_path(self, key: str) -> str:
        return os.path.join(self.directory, key.replace("/", os.sep))

    def _stat(self, key: str):
        try:
            st = os.stat(self._full_path(key))
        except OSError:
            return None
        return st.st_mtime_ns, st.st_size

    def _store(self, key: str, stat_pair) -> str:
        version = compute_file_version(self._full_path(key))
        self._entries[key] = (version, stat_pair[0], stat_pair[1])
        self.revision += 1
        return version

    # ── 공개 API ─────────────────────────────────────────────
    def refresh(self) -> int:
        """static 디렉터리를 훑어 대상 파일의 버전을 모두 다시 계산한다.

        FastAPI startup 에서 한 번 호출한다. 등록된 파일 수를 반환한다.
        """
        self._entries.clear()
        if not os.path.isdir(self.directory):
            return 0
        for root, _dirs, files in os.walk(self.directory):
            for name in files:
                if not name.lower().endswith(VERSIONED_SUFFIXES):
                    continue
                full = os.path.join(root, name)
                key = os.path.relpath(full, self.directory).replace(os.sep, "/")
                stat_pair = self._stat(key)
                if stat_pair is not None:
                    self._store(key, stat_pair)
        self.revision += 1
        return len(self._entries)

    def poll(self) -> None:
        """dev_mode 전용 — 등록된 파일의 변경을 감지해 해시를 갱신한다.

        HTML 재작성 결과는 revision 기준으로 캐시되므로, 재작성 전에 이걸 호출해야
        자산 변경이 revision 에 반영되어 캐시가 정상적으로 무효화된다.
        (호출하지 않으면 HTML 캐시가 먼저 적중해 자산 해시를 영원히 다시 읽지 않는다.)
        """
        if not self.dev_mode:
            return
        for key in list(self._entries):
            self.get(key)

    def get(self, key: str) -> str | None:
        """키에 해당하는 버전 문자열을 반환한다. 대상 파일이 아니면 None."""
        entry = self._entries.get(key)
        if entry is not None and not self.dev_mode:
            return entry[0]

        stat_pair = self._stat(key)
        if stat_pair is None:
            # 파일이 사라졌으면 기존 값 제거
            if entry is not None:
                self._entries.pop(key, None)
                self.revision += 1
            return None
        if entry is not None and (entry[1], entry[2]) == stat_pair:
            return entry[0]
        return self._store(key, stat_pair)


def _resolve_key(url_path: str, html_dir_key: str) -> str | None:
    """HTML 안의 URL 을 static 디렉터리 기준 상대 키로 변환한다.

    html_dir_key: HTML 파일이 있는 디렉터리의 static 기준 상대 경로
                  (static 루트면 "", static/landing/index.html 이면 "landing")
    """
    if url_path.startswith("/static/"):
        key = url_path[len("/static/"):]
    elif url_path.startswith("/"):
        # /static 밖의 절대 경로는 대상이 아니다
        return None
    else:
        key = f"{html_dir_key}/{url_path}" if html_dir_key else url_path

    # ./ 와 ../ 정리
    parts: list[str] = []
    for seg in key.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return None  # static 루트를 벗어남
            parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts) if parts else None


def _with_version(url: str, version: str) -> str:
    """URL 에 ?v=<version> 을 붙인다. 기존 v 파라미터는 교체한다."""
    split = urlsplit(url)
    params = [(k, val) for k, val in parse_qsl(split.query, keep_blank_values=True)
              if k != VERSION_PARAM]
    params.append((VERSION_PARAM, version))
    return urlunsplit((split.scheme, split.netloc, split.path,
                       urlencode(params), split.fragment))


def rewrite_html(html: str, versions: AssetVersions, html_dir_key: str = "") -> str:
    """HTML 안의 로컬 CSS/JS 링크에 버전 파라미터를 붙여 반환한다."""

    def replace(match: re.Match) -> str:
        url = match.group("url")
        stripped = url.strip()
        if not stripped or stripped.lower().startswith(_SKIP_PREFIXES):
            return match.group(0)

        path_only = urlsplit(stripped).path
        if not path_only.lower().endswith(VERSIONED_SUFFIXES):
            return match.group(0)

        key = _resolve_key(path_only, html_dir_key)
        if key is None:
            return match.group(0)
        version = versions.get(key)
        if version is None:
            return match.group(0)

        return f"{match.group('attr')}{match.group('quote')}" \
               f"{_with_version(stripped, version)}{match.group('quote')}"

    return _ATTR_RE.sub(replace, html)


class VersionedStaticFiles(StaticFiles):
    """StaticFiles + HTML 링크 캐시 버스팅 + Cache-Control 설정.

    HTML 은 응답 시점에 본문을 다시 쓰고(파일은 그대로), 재작성 결과는
    (mtime, size, manifest revision) 기준으로 메모리에 캐시한다.
    """

    def __init__(self, *args, versions: AssetVersions, **kwargs):
        super().__init__(*args, **kwargs)
        self.versions = versions
        # full_path -> (mtime_ns, size, revision, rewritten bytes)
        self._html_cache: dict[str, tuple[int, int, int, bytes]] = {}

    def _rewritten_html(self, full_path: str, stat_result: os.stat_result) -> bytes | None:
        # dev_mode 면 자산 변경을 먼저 반영한다. 이걸 캐시 확인보다 앞에 둬야
        # 자산만 바뀐 경우(HTML 은 그대로)에도 캐시가 무효화된다.
        self.versions.poll()

        cached = self._html_cache.get(full_path)
        revision = self.versions.revision
        if cached and cached[0] == stat_result.st_mtime_ns \
                and cached[1] == stat_result.st_size and cached[2] == revision:
            return cached[3]

        try:
            with open(full_path, "r", encoding="utf-8") as fp:
                source = fp.read()
        except (OSError, UnicodeDecodeError):
            return None  # 읽지 못하면 원본을 그대로 서빙한다

        html_dir_key = os.path.relpath(
            os.path.dirname(full_path), self.versions.directory
        ).replace(os.sep, "/")
        if html_dir_key in (".", os.curdir):
            html_dir_key = ""

        rendered = rewrite_html(source, self.versions, html_dir_key).encode("utf-8")
        self._html_cache[full_path] = (
            stat_result.st_mtime_ns, stat_result.st_size, revision, rendered,
        )
        return rendered

    def file_response(
        self,
        full_path,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        path_str = str(full_path)

        if path_str.lower().endswith(".html"):
            rendered = self._rewritten_html(path_str, stat_result)
            if rendered is not None:
                headers = {"Cache-Control": HTML_CACHE_CONTROL}
                if scope.get("method", "GET").upper() == "HEAD":
                    response = Response(
                        b"", status_code=status_code,
                        media_type="text/html; charset=utf-8", headers=headers,
                    )
                    response.headers["content-length"] = str(len(rendered))
                    return response
                return Response(
                    rendered, status_code=status_code,
                    media_type="text/html; charset=utf-8", headers=headers,
                )

        response = super().file_response(
            full_path, stat_result, scope, status_code=status_code,
        )
        # ?v= 로 요청된 정적 파일은 내용이 바뀌면 URL 도 바뀌므로 장기 캐시가 안전하다.
        if status_code == 200 and _requested_with_version(scope):
            response.headers["Cache-Control"] = VERSIONED_CACHE_CONTROL
        return response


def _requested_with_version(scope: Scope) -> bool:
    query = scope.get("query_string") or b""
    if not query:
        return False
    try:
        decoded = query.decode("latin-1")
    except (UnicodeDecodeError, AttributeError):
        return False
    return any(k == VERSION_PARAM and val for k, val in parse_qsl(decoded))
