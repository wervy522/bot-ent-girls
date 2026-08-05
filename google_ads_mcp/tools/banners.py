"""
Сборка и валидация HTML5-баннеров для Google Ads App-кампаний.

Вёрстку пишет Claude в сессии и передаёт сюда как body_html/css/js — модуль
НЕ ходит ни в какие LLM API. Его работа: собрать неломаемый каркас, положить
детерминированный ZIP и прогнать через ворота валидации.

Ворота:
  0. lint      — статические правила Google (типы файлов, чёрный список, структура)
  1. budget    — вес и число файлов
  2. render    — реальный рендер в headless Chrome + перехват внешних запросов
  3. google    — официальный валидатор Google (публичный API, бесплатный)

При strict=True путь к ZIP не возвращается, если есть хоть один FAIL.
"""
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parent.parent / "banners_spec"
OUT_ROOT = Path.home() / "Documents" / "banners"

# Ровно два размера для App-кампаний. 300x250 и прочее — это Display, другой формат.
SIZES = {"portrait": (320, 480), "landscape": (480, 320)}

# Белый список расширений. Ровно 7, .jpg формально отсутствует — только .jpeg
ALLOWED_EXT = {".css", ".gif", ".html", ".jpeg", ".js", ".png", ".svg"}

# Внешние хосты, которые Google разрешает
ALLOWED_HOSTS = (
    "fonts.googleapis.com", "fonts.gstatic.com",
    "ajax.googleapis.com", "tpc.googlesyndication.com",
)

MAX_ZIP_BYTES = 4 * 1024 * 1024      # целевой потолок; жёсткий порог Google — 5 МБ
MAX_FILES = 512

# Запрещённое, каждый пункт — реальный код отклонения
FORBIDDEN = [
    (r"<iframe|<frame\b|<frameset", "iframe/frame запрещены (assets in child frames)"),
    (r"Enabler\.js|s0\.2mdn\.net|studio\.googleusercontent", "DoubleClick Studio → DOUBLECLICK_BUNDLE_NOT_ALLOWED"),
    (r"swiffy", "Swiffy → SWIFFY_BUNDLE_NOT_ALLOWED"),
    (r"<audio\b", "тег audio прямо назван в политике как нарушение"),
    (r"cdn\.ampproject\.org|<amp-", "AMPHTML в App-кампаниях не поддерживается"),
    (r"localStorage|sessionStorage|document\.cookie",
     "креатив крутится в sandbox без allow-same-origin — будет SecurityError"),
    (r"document\.write", "document.write не использовать"),
    (r'<meta[^>]+name=["\'](?:productType|vertical)', "фидовые HTML5 не поддерживаются"),
]

EXITAPI = "https://tpc.googlesyndication.com/pagead/gadgets/html5/api/exitapi.js"


# ── Каркас ────────────────────────────────────────────────────────────────

def _skeleton(body_html: str, css: str, js: str, orientation: str,
              dh_min: int, dh_max: int, exit_api: bool = True) -> str:
    """
    Собрать полный index.html. Всё, что может завалить модерацию — DOCTYPE,
    мета-теги, литеральный тег exitapi.js, reset, движок резиновости — пишется
    здесь кодом, а не моделью. Модель отвечает только за содержимое сцены.
    """
    dw, dh = SIZES[orientation]
    fit_js = (SPEC_DIR / "fit.js").read_text(encoding="utf-8")
    exit_tag = f'<script src="{EXITAPI}"></script>\n' if exit_api else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="ad.size" content="width={dw},height={dh}">
<meta name="ad.orientation" content="{orientation}">
{exit_tag}<style>
html,body{{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#000}}
*{{box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
#bleed{{position:fixed;left:0;top:0;width:100%;height:100%;z-index:0}}
#stage{{position:absolute;left:0;top:0;width:{dw}px;height:{dh}px;
  transform-origin:top left;z-index:1;overflow:hidden}}
#hit{{position:fixed;inset:0;z-index:99;cursor:pointer;background:transparent}}
{css}
</style>
</head>
<body>
<div id="bleed"></div>
<div id="stage">
{body_html}
</div>
<script>
window.__DW={dw};window.__DHMIN={dh_min};window.__DHMAX={dh_max};
</script>
<script>
{fit_js}
</script>
<script>
function adExit(){{ try{{ if(window.ExitApi&&ExitApi.exit){{ExitApi.exit();return;}} }}catch(e){{}} }}
{js}
</script>
</body>
</html>
"""


# ── Детерминированный ZIP ─────────────────────────────────────────────────

def _write_zip(path: Path, files: dict[str, bytes]) -> bytes:
    """
    Плоский детерминированный архив: сортированные имена, фиксированная дата,
    максимальное сжатие. Детерминизм нужен, чтобы одинаковый контент давал
    одинаковый sha256 — на этом держится проверка «залито именно проверенное».
    Никаких папок, никакого __MACOSX — сборка только через zipfile.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(files):
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, files[name])
    data = buf.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


# ── Ворота 0-1: статика ───────────────────────────────────────────────────

def _lint(files: dict[str, bytes], orientation: str) -> list[dict]:
    issues = []

    def fail(rule, msg, fix=""):
        issues.append({"level": "FAIL", "rule": rule, "msg": msg, "fix": fix})

    def warn(rule, msg, fix=""):
        issues.append({"level": "WARN", "rule": rule, "msg": msg, "fix": fix})

    if "index.html" not in files:
        fail("primary-entry", "нет index.html в корне",
             "MISSING_PRIMARY_MEDIA_BUNDLE_ENTRY, и banner-viewer тоже не откроет")

    for name in files:
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED_EXT:
            fail("file-type", f"{name}: расширение {ext} вне белого списка",
                 f"разрешены только {' '.join(sorted(ALLOWED_EXT))}; .jpg невалиден, нужен .jpeg")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            fail("file-name", f"{name}: недопустимые символы в имени",
                 "только [A-Za-z0-9._-], без пробелов и кириллицы")
        if "/" in name:
            fail("flat-zip", f"{name}: вложенная папка", "архив должен быть плоским")
        if name.startswith("__MACOSX") or name.endswith(".DS_Store"):
            fail("junk", f"{name}: мусорный файл macOS", "собирать только через zipfile")
        if len(files[name]) == 0:
            fail("empty-file", f"{name}: нулевой размер", "")

    html = files.get("index.html", b"").decode("utf-8", "ignore")

    for pattern, msg in FORBIDDEN:
        if re.search(pattern, html, re.I):
            fail("forbidden", msg, "")

    for tag in ("<!DOCTYPE html>", "<html", "<body"):
        if tag.lower() not in html.lower():
            fail("structure", f"нет обязательного {tag}", "")

    if "ad.orientation" not in html:
        fail("meta", "нет meta ad.orientation", "без него отрендерят только portrait")
    if "ad.size" not in html:
        warn("meta", "нет meta ad.size", "banner-viewer.html читает только его")

    # внешние ссылки — грепом; рантайм-URL ловятся на воротах render
    for url in re.findall(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', html, re.I):
        host = re.sub(r"^https?://([^/]+).*", r"\1", url)
        if not any(host.endswith(h) for h in ALLOWED_HOSTS):
            fail("external-url", f"внешний ресурс вне белого списка: {host}",
                 "EXTERNAL_URL_NOT_ALLOWED; всё кроме Google Fonts/jQuery/GSAP/tpc кладём внутрь ZIP")

    # самозакрывающиеся SVG-теги Google не принимает
    for m in re.findall(r"<(path|circle|rect|line|polygon|ellipse)\b[^>]*/>", html, re.I):
        fail("svg-selfclose", f"<{m} .../> — самозакрывающийся тег",
             f"писать явно: <{m} ...></{m}>")

    for junk in ("rdf:", "inkscape:", "sodipodi:", "<metadata"):
        if junk in html:
            warn("svg-junk", f"мусор редактора в SVG: {junk}", "вычистить, риск UNSUPPORTED_HTML5_FEATURE")

    # ссылки на файлы, которых нет в бандле
    for ref in re.findall(r'(?:src|href)\s*=\s*["\'](?!https?:|data:|#)([^"\']+)', html, re.I):
        if ref not in files:
            fail("missing-asset", f"ссылка на отсутствующий файл: {ref}", "INVALID_URL_REFERENCE")

    if EXITAPI not in html:
        warn("exitapi", "нет литерального тега exitapi.js",
             "Google подставит свою кнопку Install и весь баннер станет кликабельным")
    elif "ExitApi.exit" not in html and "adExit" not in html:
        warn("exitapi", "exitapi.js подключён, но exit() нигде не вызывается", "")

    if re.search(r"clickTag", html, re.I):
        warn("clicktag", "clickTag — конвенция CM360/DV360, в Google Ads не существует",
             "использовать ExitApi.exit()")

    return issues


def _budget(data: bytes, files: dict[str, bytes]) -> list[dict]:
    out = []
    if len(data) > MAX_ZIP_BYTES:
        out.append({"level": "FAIL", "rule": "zip-size",
                    "msg": f"{len(data)/1024/1024:.2f} МБ > лимита {MAX_ZIP_BYTES/1024/1024:.0f} МБ",
                    "fix": "пережать картинки"})
    if len(files) > MAX_FILES:
        out.append({"level": "FAIL", "rule": "file-count",
                    "msg": f"{len(files)} файлов > {MAX_FILES}", "fix": ""})
    return out


# ── Ворота 2: рендер в Chrome ─────────────────────────────────────────────

def _chrome() -> str | None:
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium")):
        if p and os.path.exists(p):
            return p
    return None


def _shoot(files: dict[str, bytes], viewports: list[tuple[int, int]], scale: int = 2,
           out_dir: Path = None, stem: str = "shot", settle_ms: int = 1800):
    """
    Отрендерить бандл в заданных вьюпортах через Playwright.

    Именно Playwright, а не Chrome CLI: флаг --window-size в headless-режиме
    молча игнорируется, страница всегда получает innerWidth=500. Для нас это
    смертельно — fit.js масштабирует сцену по innerWidth, и весь рендер-гейт
    проверял бы вёрстку не на том вьюпорте, на котором мы думаем.

    Возвращает (список PIL.Image, список путей, список ошибок консоли).
    """
    from playwright.sync_api import sync_playwright

    imgs, paths, errors = [], [], []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for n, b in files.items():
            (d / n).write_bytes(b)
        url = (d / "index.html").as_uri()

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            for vw, vh in viewports:
                page = browser.new_page(viewport={"width": vw, "height": vh},
                                        device_scale_factor=scale)
                external = []
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                page.on("request", lambda r: external.append(r.url)
                        if r.url.startswith(("http://", "https://")) else None)
                try:
                    page.goto(url, wait_until="load", timeout=20000)
                    page.wait_for_timeout(settle_ms)
                    # каскадные появления идут ~1.2-1.5с: снимать раньше — значит
                    # поймать полупрозрачные элементы и решить, что их нет вовсе
                    try:
                        page.wait_for_function(
                            "() => document.getAnimations().filter("
                            "a => a.playState==='running' && "
                            "(a.effect?.getTiming?.().iterations||1) !== Infinity).length === 0",
                            timeout=6000)
                    except Exception:
                        pass                      # бесконечные анимации — не ждём

                    # переполнение меряем в DOM, а не по пикселям: у баннера с
                    # градиентом край кадра всегда пёстрый, и эвристика по цветам
                    # даёт ложные срабатывания
                    over = page.evaluate("""() => {
                        const st = document.getElementById('stage');
                        if (!st) return null;
                        const out = [];
                        const box = st.getBoundingClientRect();
                        for (const el of st.querySelectorAll('*')) {
                            const r = el.getBoundingClientRect();
                            if (r.width === 0 || r.height === 0) continue;
                            const dx = Math.max(box.left - r.left, r.right - box.right);
                            const dy = Math.max(box.top - r.top, r.bottom - box.bottom);
                            if (dx > 1 || dy > 1) out.push({
                                tag: el.tagName.toLowerCase(),
                                cls: (el.className || '').toString().slice(0, 24),
                                dx: Math.round(dx), dy: Math.round(dy),
                            });
                        }
                        return {clipped: out.slice(0, 4),
                                scrollX: st.scrollWidth - st.clientWidth,
                                scrollY: st.scrollHeight - st.clientHeight};
                    }""")
                    if over:
                        for c in over.get("clipped", []):
                            errors.append(
                                f"__CLIP__{vw}x{vh}|<{c['tag']}{'.' + c['cls'] if c['cls'] else ''}> "
                                f"вылезает за сцену на {max(c['dx'], c['dy'])}px")

                    dst = (out_dir / f"{stem}_{vw}x{vh}.png") if out_dir else (d / f"{stem}_{vw}x{vh}.png")
                    if out_dir:
                        out_dir.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(dst))
                    from PIL import Image
                    imgs.append((vw, vh, Image.open(dst).convert("RGB")))
                    paths.append(str(dst))
                except Exception as e:
                    errors.append(f"рендер {vw}x{vh}: {str(e)[:100]}")
                # внешние запросы, собранные в рантайме — регексом их не поймать
                for u in external:
                    host = re.sub(r"^https?://([^/]+).*", r"\1", u)
                    if not any(host.endswith(h) for h in ALLOWED_HOSTS):
                        errors.append(f"__EXTERNAL__{host}")
                page.close()
            browser.close()
    return imgs, paths, errors


def _render_check(files: dict[str, bytes], orientation: str) -> list[dict]:
    """
    Рендер настоящим браузером в трёх вьюпортах. Ловит то, что статикой не
    поймать: пустой баннер, обрезанный контент, JS-ошибки и внешние запросы,
    собранные в рантайме.
    """
    dw, dh = SIZES[orientation]
    # штатный размер + два реальных слота, на которых проверяем резиновость
    vps = [(dw, dh), (360, 640), (414, 896)] if orientation == "portrait" \
        else [(dw, dh), (640, 360), (896, 414)]

    try:
        imgs, _, errors = _shoot(files, vps, scale=1)
    except Exception as e:
        return [{"level": "WARN", "rule": "render",
                 "msg": f"рендер-гейт пропущен: {str(e)[:90]}", "fix": ""}]

    issues = []
    for host in {e[12:] for e in errors if e.startswith("__EXTERNAL__")}:
        issues.append({"level": "FAIL", "rule": "external-runtime",
                       "msg": f"внешний запрос в рантайме: {host}",
                       "fix": "EXTERNAL_URL_NOT_ALLOWED; положить ресурс внутрь ZIP"})
    for clip in [e[8:] for e in errors if e.startswith("__CLIP__")][:4]:
        vp, what = clip.split("|", 1)
        issues.append({"level": "WARN", "rule": "clipped",
                       "msg": f"{vp}: {what}",
                       "fix": "элемент обрезается #stage — уменьши кегль или отступы"})
    for err in [e for e in errors if not e.startswith(("__EXTERNAL__", "__CLIP__"))][:3]:
        issues.append({"level": "WARN", "rule": "console", "msg": f"ошибка в консоли: {err[:110]}", "fix": ""})

    if not imgs:
        return issues + [{"level": "FAIL", "rule": "render", "msg": "не удалось отрендерить", "fix": ""}]

    for vw, vh, im in imgs:
        colors = im.getcolors(maxcolors=1_000_000) or []
        if len(colors) <= 2:
            issues.append({"level": "FAIL", "rule": "blank",
                           "msg": f"{vw}x{vh}: баннер визуально пустой ({len(colors)} цветов)",
                           "fix": "контент должен лежать внутри #stage"})
        elif len(colors) < 12:
            issues.append({"level": "WARN", "rule": "sparse",
                           "msg": f"{vw}x{vh}: очень бедная картинка ({len(colors)} цветов)", "fix": ""})

    return issues


# ── Ворота 3: официальный валидатор Google ────────────────────────────────

# Проверки валидатора, которые для App-кампаний неприменимы.
#
# «Ad Dimensions» гоняет размер по списку DISPLAY-форматов: 300x250 там проходит,
# а 320x480 — нет. Но для App-кампаний 320x480 как раз и есть правильный размер,
# и Google Ads API такой бандл принимает (проверено заливкой). То есть на App
# эта проверка даёт ложный FAIL, и мы понижаем её до INFO.
DISPLAY_ONLY_CHECKS = {"Ad Dimensions"}


def _google_validate(data: bytes, app_campaign: bool = True) -> list[dict]:
    """
    Официальный валидатор Google (h5validator). Бесплатный, без ключа.
    Асинхронный: POST multipart отдаёт id, результат забирается отдельным GET.
    """
    import urllib.request
    import uuid

    def _post_multipart(url: str, field: str, filename: str, payload: bytes):
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: application/zip\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    def _unwrap(raw: bytes) -> dict:
        # ответ префиксован защитой от JSON-hijacking: )]}',\n
        txt = raw.decode("utf-8", "ignore").lstrip()
        if txt.startswith(")]}'"):
            txt = txt.split("\n", 1)[1]
        return json.loads(txt)

    import time
    try:
        posted = _unwrap(_post_multipart(
            "https://h5validator.appspot.com/api/policy/adwords",
            "creative_bundle", "bundle.zip", data))
        if not posted.get("status"):
            return [{"level": "WARN", "rule": "google-api",
                     "msg": f"валидатор отклонил загрузку: {posted.get('error')}", "fix": ""}]
        rid = posted["response"]["result"]

        cases = []
        for _ in range(6):                      # результат готовится пару секунд
            time.sleep(2)
            with urllib.request.urlopen(
                f"https://h5validator.appspot.com/api/policy/adwords/result/{rid}", timeout=45
            ) as r:
                res = _unwrap(r.read())
            cases = (res.get("response", {}).get("result", {}) or {}).get("validation_case_results") or []
            if cases:
                break
        if not cases:
            return [{"level": "WARN", "rule": "google-api", "msg": "валидатор не отдал результат", "fix": ""}]
    except Exception as e:
        return [{"level": "WARN", "rule": "google-api",
                 "msg": f"валидатор Google недоступен: {str(e)[:90]}", "fix": ""}]

    out, passed = [], 0
    for c in cases:
        name, status = c.get("name", "?"), c.get("status")
        msgs = "; ".join(c.get("error_messages") or [])
        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            if app_campaign and name in DISPLAY_ONLY_CHECKS:
                out.append({"level": "INFO", "rule": f"google:{name}",
                            "msg": f"{msgs} — проверка из Display-политики, для App неприменима",
                            "fix": ""})
            else:
                out.append({"level": "FAIL", "rule": f"google:{name}", "msg": msgs, "fix": ""})
        elif status == "WARN":
            out.append({"level": "WARN", "rule": f"google:{name}", "msg": msgs, "fix": ""})
    out.append({"level": "INFO", "rule": "google",
                "msg": f"валидатор Google: {passed}/{len(cases)} проверок пройдено", "fix": ""})
    return out


# ── Публичные функции ─────────────────────────────────────────────────────

def build_banner(app: str, slug: str, body_html: str, css: str = "", js: str = "",
                 orientation: str = "portrait", images: dict = None,
                 dh_min: int = 400, dh_max: int = 720, exit_api: bool = True,
                 concept: str = "", strict: bool = True,
                 render: bool = True, online: bool = True) -> dict:
    """
    Собрать баннер из вёрстки и прогнать через ворота.

    body_html — содержимое сцены (внутрь #stage), без html/head/body
    css / js   — стили и скрипт, каркас добавляется автоматически
    images     — {"имя_в_zip.png": "/путь/на/диске"}; расширение только из белого списка
    dh_min/dh_max — в каких пределах тянется высота сцены при масштабировании
    strict     — при FAIL путь к ZIP не возвращается
    """
    if orientation not in SIZES:
        raise ValueError(f"orientation: portrait | landscape, получено {orientation!r}")

    html = _skeleton(body_html, css, js, orientation, dh_min, dh_max, exit_api)
    files: dict[str, bytes] = {"index.html": html.encode("utf-8")}

    for name, src in (images or {}).items():
        p = Path(src).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"нет файла для {name}: {src}")
        files[name] = p.read_bytes()

    out_dir = OUT_ROOT / app / "zip"
    zip_path = out_dir / f"{slug}_{SIZES[orientation][0]}x{SIZES[orientation][1]}.zip"
    data = _write_zip(zip_path, files)

    issues = _lint(files, orientation) + _budget(data, files)
    if render:
        issues += _render_check(files, orientation)
    if online:
        issues += _google_validate(data, app_campaign=True)

    fails = [i for i in issues if i["level"] == "FAIL"]
    warns = [i for i in issues if i["level"] == "WARN"]

    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    report = {
        "app": app, "slug": slug, "orientation": orientation, "concept": concept,
        "size": f"{SIZES[orientation][0]}x{SIZES[orientation][1]}",
        "bytes": len(data), "kb": round(len(data) / 1024, 1),
        "files": sorted(files), "sha256": sha,
        "passed": not fails, "fails": fails, "warns": warns,
    }
    (out_dir / f"{slug}.report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if fails and strict:
        report["zip_path"] = None
        report["error"] = f"{len(fails)} FAIL — ZIP собран, но не выдан. Почини и пересобери."
    else:
        report["zip_path"] = str(zip_path)
    return report


def validate_banner(zip_path: str, render: bool = True, online: bool = True,
                    app_campaign: bool = True) -> dict:
    """Проверить любой ZIP, в том числе собранный не нами."""
    p = Path(zip_path).expanduser()
    data = p.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}

    html = files.get("index.html", b"").decode("utf-8", "ignore")
    m = re.search(r'ad\.orientation["\'\s]+content=["\']([a-z]+)', html)
    orientation = m.group(1) if m and m.group(1) in SIZES else "portrait"

    issues = _lint(files, orientation) + _budget(data, files)
    if render:
        issues += _render_check(files, orientation)
    if online:
        issues += _google_validate(data, app_campaign=True)

    fails = [i for i in issues if i["level"] == "FAIL"]
    return {
        "zip": str(p), "kb": round(len(data) / 1024, 1), "orientation": orientation,
        "files": sorted(files), "passed": not fails,
        "fails": fails, "warns": [i for i in issues if i["level"] == "WARN"],
    }


def preview_banner(zip_path: str, scale: int = 2, viewports: list = None,
                   settle_ms: int = 1800) -> dict:
    """
    Отрендерить баннер в PNG в нескольких вьюпортах — посмотреть глазами,
    что резиновость не сломалась на нестандартном слоте.
    """
    p = Path(zip_path).expanduser()
    with zipfile.ZipFile(p) as z:
        files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}

    vps = [tuple(int(x) for x in v.split("x")) for v in
           (viewports or ["320x480", "360x640", "414x896"])]
    out_dir = OUT_ROOT / p.parent.parent.name / "preview"
    try:
        _, shots, errors = _shoot(files, vps, scale=scale, out_dir=out_dir, stem=p.stem, settle_ms=settle_ms)
    except Exception as e:
        return {"error": f"рендер не удался: {str(e)[:120]}"}
    return {"zip": str(p), "shots": shots,
            "viewports": [f"{w}x{h}" for w, h in vps],
            "console_errors": [e for e in errors if not e.startswith("__EXTERNAL__")]}


# ── Графика ───────────────────────────────────────────────────────────────

# Формулировка выстрадана: любое упоминание «зон», «третей» или «места под текст»
# модель понимает буквально и рисует леттербокс-полосы с резкой границей.
# Поэтому — только цельность кадра, а место под текст делается скримом в CSS.
ART_NEG = ("single continuous photograph filling the entire frame, "
           "uninterrupted composition from edge to edge, "
           "no letterboxing, no black bars, no horizontal bands, no split panels, "
           "no borders, no frame, no vignette edges, "
           "no text, no logos, no watermarks, no captions, no UI elements")


def _detect_bands(im, tol: int = 26) -> list[str]:
    """
    Найти горизонтальные полосы — резкие перепады яркости по всей ширине кадра.
    Именно так выглядит леттербокс, который модель рисует, если в промпте
    хоть как-то намекнуть на «зону под текст».
    """
    g = im.convert("L")
    w, h = g.size
    step = max(1, w // 64)
    rows = []
    for y in range(h):
        px = [g.getpixel((x, y)) for x in range(0, w, step)]
        rows.append(sum(px) / len(px))

    hits = []
    for y in range(4, h - 4):
        # средняя яркость до и после границы, с зазором в пару строк
        before = sum(rows[y - 4:y - 1]) / 3
        after = sum(rows[y + 2:y + 5]) / 3
        if abs(after - before) > tol:
            hits.append((y, round(after - before)))

    # склеиваем соседние срабатывания в одну границу
    bands, last = [], -99
    for y, d in hits:
        if y - last > h * 0.04:
            bands.append(f"y={round(y / h * 100)}% перепад {d:+d}")
        last = y
    return bands[:4]


def generate_art(app: str, prompt: str, out_name: str, orientation: str = "portrait",
                 model: str = "google/gemini-3-pro-image", quality: str = "2K",
                 max_kb: int = 500, retry_on_bands: int = 1) -> dict:
    """
    Сгенерировать растровый фон для баннера. Единственная платная операция
    во всём конвейере (~$0.14 за картинку на gemini-3-pro-image в 2K).

    Кладёт готовый файл в library приложения и возвращает путь для images=.
    """
    import os as _os
    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

    if not out_name.lower().endswith((".jpeg", ".png")):
        raise ValueError("out_name должен оканчиваться на .jpeg или .png (.jpg невалиден для Google)")

    aspect = "2:3" if orientation == "portrait" else "3:2"
    cl = OpenAI(api_key=_os.environ["OPENROUTER_API_KEY"],
                base_url="https://openrouter.ai/api/v1")

    import base64
    from PIL import Image

    def _one(extra_hint: str = ""):
        r = cl.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"{prompt}. {ART_NEG}{extra_hint}"}],
            extra_body={"image_config": {"aspect_ratio": aspect, "image_size": quality}},
        )
        imgs = getattr(r.choices[0].message, "images", None) or []
        if not imgs:
            raise RuntimeError("модель не вернула изображение")
        b, bpx = None, -1
        for im in imgs:
            raw = base64.b64decode(im["image_url"]["url"].split(",", 1)[1])
            pil = Image.open(io.BytesIO(raw))
            px = pil.size[0] * pil.size[1]
            if px > bpx:                      # pro отдаёт превью И полноразмер
                b, bpx = pil, px              # берём по площади, не первый
        return b, getattr(r.usage, "cost", 0) or 0

    best, spent = _one()
    bands = _detect_bands(best)
    tries = 0
    while bands and tries < retry_on_bands:   # полосы — брак, переснимаем
        tries += 1
        again, c = _one(" The photograph must be one seamless continuous image "
                        "with absolutely no horizontal dividing lines anywhere.")
        spent += c
        if not _detect_bands(again):
            best, bands = again, []
            break
        best = again if len(_detect_bands(again)) < len(bands) else best
        bands = _detect_bands(best)

    dw, dh = SIZES[orientation]
    target = dw / dh
    w, h = best.size
    if w / h > target:                        # кроп по центру в точный аспект
        nw = int(h * target)
        best = best.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / target)
        best = best.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))

    lib = OUT_ROOT / app / "library"
    lib.mkdir(parents=True, exist_ok=True)
    dst = lib / out_name
    best = best.convert("RGB")
    for q in (90, 82, 74, 66):
        best.save(dst, "JPEG" if dst.suffix == ".jpeg" else "PNG",
                  quality=q, optimize=True, progressive=True)
        if dst.stat().st_size <= max_kb * 1024 or dst.suffix != ".jpeg":
            break

    out = {"path": str(dst), "name": out_name, "size": list(best.size),
           "kb": round(dst.stat().st_size / 1024, 1), "orientation": orientation,
           "cost_usd": round(spent, 4), "model": model, "retries": tries}
    if bands:
        out["warning"] = ("похоже на леттербокс-полосы: " + "; ".join(bands) +
                          ". Кадр лучше переснять — в промпте не должно быть "
                          "упоминаний зон, третей или места под текст.")
    return out


def render_text_image(app: str, out_name: str, html: str, width: int, height: int,
                      scale: int = 3) -> dict:
    """
    Отрендерить кусок HTML в прозрачный PNG настоящим браузером.
    Нужно для фирменных шрифтов: шрифтовые файлы в бандл класть нельзя,
    а Google Fonts в рантайме может не догрузиться.
    """
    chrome = _chrome()
    if not chrome:
        return {"error": "Chrome не найден"}
    lib = OUT_ROOT / app / "library"
    lib.mkdir(parents=True, exist_ok=True)
    dst = lib / out_name

    page = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
            f'html,body{{margin:0;padding:0;width:{width}px;height:{height}px;'
            f'background:transparent}}</style></head><body>{html}</body></html>')
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "t.html"
        src.write_text(page, encoding="utf-8")
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             "--default-background-color=00000000", "--virtual-time-budget=2000",
             f"--force-device-scale-factor={scale}", f"--window-size={width},{height}",
             f"--screenshot={dst}", src.as_uri()],
            capture_output=True, timeout=60)
    if not dst.exists():
        return {"error": "рендер не удался"}
    return {"path": str(dst), "name": out_name, "kb": round(dst.stat().st_size / 1024, 1)}


def read_spec() -> str:
    """Свод правил вёрстки для модели."""
    return (SPEC_DIR / "GUIDE.md").read_text(encoding="utf-8")
