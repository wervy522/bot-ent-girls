"""
Google Ads MCP Server — управление UAC iOS кампаниями.
"""
import os
import subprocess
from mcp.server.fastmcp import FastMCP
from .client import get_client, get_customer_id
from .tools import campaigns, assets, search, geo

_VPS_HOST = "root@68.183.223.89"
_VPS_KEY = os.path.expanduser("~/.ssh/google_ads_rotator")
_VPS_SERVICE = "google-ads-rotator"  # template service name (without @)
_SSH_OPTS = ["-i", _VPS_KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]


def _ssh(cmd: str) -> tuple[int, str]:
    """Выполнить команду на VPS, вернуть (returncode, output)."""
    result = subprocess.run(
        ["ssh"] + _SSH_OPTS + [_VPS_HOST, cmd],
        capture_output=True, text=True
    )
    return result.returncode, (result.stdout + result.stderr).strip()

mcp = FastMCP("google-ads")

# ── Известные аккаунты под MCC 5620307019 (Blue Hat) ───────────────────────
KNOWN_ACCOUNTS = {
    "Pure":          "6581104929",   # дефолтный
    "PB_new_new":    "6658090517",   # 665-809-0517
    "PDF_New":       "6829511974",   # 682-951-1974
    "SowlWeb25":     "5014521678",   # 501-452-1678
    "PDF-Reader":    "5670102394",
    "iDefNet VPN":   "9285227682",
    "Guru cleaner":  "8027081917",
    "Chattera IOS":  "7287138580",
    "Nuero":         "4525725117",
    "Pure_v2":       "7510430639",
    "AIGO Tier-3":   "4285467693",
    "Cleaner-AD_1":  "3023760603",   # 302-376-0603
    "Cleaner-AD_2":  "9033532211",   # 903-353-2211
    "Cleaner-AD_3":  "9222917248",   # 922-291-7248
    "Cleaner-AD_4":  "9438831076",   # 943-883-1076
}

# ── Campaigns ──────────────────────────────────────────────────────────────

def _cid(customer_id: str = None) -> str:
    return customer_id.replace("-", "") if customer_id else get_customer_id()


@mcp.tool()
def list_campaigns(status_filter: str = "ENABLED", customer_id: str = None) -> list[dict]:
    """
    Список UAC (App) кампаний.
    status_filter: ENABLED | PAUSED | ALL
    customer_id — опционально. Известные аккаунты:
      Pure=6581104929 (дефолт), PB_new_new=6658090517 (665-809-0517),
      PDF_New=6829511974 (682-951-1974), SowlWeb25=5014521678 (501-452-1678),
      PDF-Reader=5670102394, iDefNet VPN=9285227682, Guru cleaner=8027081917,
      Chattera IOS=7287138580, Nuero=4525725117, Pure_v2=7510430639.
    """
    return campaigns.list_campaigns(get_client(), _cid(customer_id), status_filter)


@mcp.tool()
def get_campaign(campaign_id: str, customer_id: str = None) -> dict:
    """Детальная информация о кампании по ID."""
    return campaigns.get_campaign(get_client(), _cid(customer_id), campaign_id)


@mcp.tool()
def update_campaign_status(campaign_id: str, status: str, customer_id: str = None) -> dict:
    """
    Изменить статус кампании.
    status: ENABLED | PAUSED
    """
    return campaigns.update_campaign_status(get_client(), _cid(customer_id), campaign_id, status)


@mcp.tool()
def get_campaign_metrics(campaign_id: str, date_range: str = "LAST_30_DAYS", customer_id: str = None) -> dict:
    """
    Метрики кампании: impressions, clicks, conversions, cost.
    date_range: TODAY | LAST_7_DAYS | LAST_30_DAYS | THIS_MONTH | LAST_MONTH
    """
    return campaigns.get_campaign_metrics(get_client(), _cid(customer_id), campaign_id, date_range)


# ── Asset Groups (UAC ads) ─────────────────────────────────────────────────

@mcp.tool()
def list_asset_groups(campaign_id: str, customer_id: str = None) -> list[dict]:
    """Список asset groups для UAC кампании."""
    return assets.list_asset_groups(get_client(), _cid(customer_id), campaign_id)


@mcp.tool()
def get_asset_group(asset_group_id: str, customer_id: str = None) -> dict:
    """Все assets (заголовки, тексты, картинки, видео) одной asset group."""
    return assets.get_asset_group(get_client(), _cid(customer_id), asset_group_id)


@mcp.tool()
def add_text_asset(asset_group_id: str, text: str, field_type: str, customer_id: str = None) -> dict:
    """
    Добавить текстовый asset в asset group.
    field_type: HEADLINE | DESCRIPTION | LONG_HEADLINE
    """
    return assets.add_text_asset(get_client(), _cid(customer_id), asset_group_id, text, field_type)


@mcp.tool()
def remove_text_asset(asset_group_id: str, asset_group_asset_resource_name: str, customer_id: str = None) -> dict:
    """
    Удалить текстовый asset из asset group.
    Передай resource_name из get_asset_group.
    """
    return assets.remove_text_asset(get_client(), _cid(customer_id), asset_group_asset_resource_name)


@mcp.tool()
def list_ad_group_ads(campaign_id: str, customer_id: str = None) -> list[dict]:
    """
    Список всех App Ads кампании с их ad_id, ad_group, текущими заголовками и описаниями.
    Используй чтобы узнать ad_id перед вызовом update_app_ad_texts.
    """
    return assets.list_ad_group_ads(get_client(), _cid(customer_id), campaign_id)


@mcp.tool()
def update_app_ad_texts(
    ad_id: str,
    headlines: list[str],
    descriptions: list[str],
    customer_id: str = None,
) -> dict:
    """
    Заменить заголовки и описания в App Ad.
    Нужно передать ровно 2 заголовка (до 30 символов) и 1 описание (до 90 символов).
    ad_id — получи через list_ad_group_ads.
    """
    return assets.update_app_ad_texts(get_client(), _cid(customer_id), ad_id, headlines, descriptions)


@mcp.tool()
def create_app_ad(
    ad_group_id: str,
    headlines: list[str],
    descriptions: list[str],
    customer_id: str = None,
) -> dict:
    """
    Создать новое App Ad в группе объявлений UAC-кампании.
    headlines: минимум 2 заголовка (до 30 символов каждый).
    descriptions: минимум 1 описание (до 90 символов каждое).
    ad_group_id — получи через list_ad_groups или create_ad_group.
    После создания используй upload_html5_banner чтобы добавить HTML5-баннеры.
    """
    return assets.create_app_ad(get_client(), _cid(customer_id), ad_group_id, headlines, descriptions)



@mcp.tool()
def start_rotation(campaign_id: str, customer_id: str = None) -> dict:
    """
    Запустить автоматическую ротацию заголовков и описаний на VPS (работает 24/7).
    Каждые 25–35 минут подставляются новые уникальные тексты.
    campaign_id — ID кампании (получи через list_campaigns).
    customer_id — опционально, если кампания в другом аккаунте.
    Можно запускать одновременно для нескольких кампаний.
    Чтобы остановить — вызови stop_rotation.
    """
    if customer_id:
        # Отдельный service файл для нестандартного аккаунта
        cid_clean = customer_id.replace("-", "")
        svc = f"{_VPS_SERVICE}-{campaign_id}"
        rc, out = _ssh(f"systemctl is-active {svc}")
        if out.strip() == "active":
            return {"status": "already_running", "campaign_id": campaign_id}
        _ssh(
            f"printf '[Unit]\\nDescription=Google Ads Rotator {campaign_id} account {cid_clean}\\n"
            f"After=network.target\\n\\n"
            f"[Service]\\nType=simple\\nWorkingDirectory=/opt/google-ads-rotator\\n"
            f"EnvironmentFile=/opt/google-ads-rotator/.env\\n"
            f"Environment=GOOGLE_ADS_CUSTOMER_ID={cid_clean}\\n"
            f"ExecStart=/opt/google-ads-rotator/venv/bin/python -m google_ads_mcp.rotator {campaign_id} {cid_clean}\\n"
            f"Restart=always\\nRestartSec=30\\n"
            f"StandardOutput=append:/var/log/google-ads-rotator-{campaign_id}.log\\n"
            f"StandardError=append:/var/log/google-ads-rotator-{campaign_id}.log\\n\\n"
            f"[Install]\\nWantedBy=multi-user.target\\n'"
            f" > /etc/systemd/system/{svc}.service"
        )
        _ssh("systemctl daemon-reload")
    else:
        svc = f"{_VPS_SERVICE}@{campaign_id}"
        rc, out = _ssh(f"systemctl is-active {svc}")
        if out.strip() == "active":
            return {"status": "already_running", "campaign_id": campaign_id}

    rc, out = _ssh(f"systemctl start {svc}")
    return {
        "status": "started" if rc == 0 else "error",
        "campaign_id": campaign_id,
        "customer_id": customer_id or "default",
        "interval": "18–23 мин",
        "log": f"/var/log/google-ads-rotator-{campaign_id}.log",
        "detail": out or "ok",
    }


@mcp.tool()
def stop_rotation(campaign_id: str) -> dict:
    """
    Остановить ротацию для конкретной кампании на VPS.
    campaign_id — ID кампании.
    """
    # Пробуем оба варианта именования сервиса
    svc_template = f"{_VPS_SERVICE}@{campaign_id}"
    svc_custom = f"{_VPS_SERVICE}-{campaign_id}"
    _, active_t = _ssh(f"systemctl is-active {svc_template}")
    _, active_c = _ssh(f"systemctl is-active {svc_custom}")

    stopped = []
    if active_t.strip() == "active":
        _ssh(f"systemctl stop {svc_template}")
        stopped.append(svc_template)
    if active_c.strip() == "active":
        _ssh(f"systemctl stop {svc_custom}")
        # Удаляем созданный service файл
        _ssh(f"rm -f /etc/systemd/system/{svc_custom}.service && systemctl daemon-reload")
        stopped.append(svc_custom)

    return {
        "status": "stopped" if stopped else "not_running",
        "campaign_id": campaign_id,
        "stopped_services": stopped,
    }


@mcp.tool()
def start_smile_rotation(campaign_id: str, customer_id: str = None) -> dict:
    """
    Запустить smile-ротацию (заголовки с эмодзи 🤔🚀💡) на VPS (работает 24/7).
    Каждые 18–22 минуты подставляются 2 новых заголовка с эмодзи + 1 описание.
    campaign_id — ID кампании (получи через list_campaigns).
    customer_id — опционально. Известные аккаунты:
      Pure=6581104929 (дефолт), PB_new_new=6658090517 (665-809-0517),
      PDF_New=6829511974 (682-951-1974), SowlWeb25=5014521678 (501-452-1678).
    Чтобы остановить — вызови stop_smile_rotation.
    """
    cid_clean = customer_id.replace("-", "") if customer_id else None
    svc = f"google-ads-smile-{campaign_id}"

    rc, out = _ssh(f"systemctl is-active {svc}")
    if out.strip() == "active":
        return {"status": "already_running", "campaign_id": campaign_id}

    exec_args = f"{campaign_id}" + (f" {cid_clean}" if cid_clean else "")
    env_line = f"Environment=GOOGLE_ADS_CUSTOMER_ID={cid_clean}\n" if cid_clean else ""

    _ssh(
        f"printf '[Unit]\\nDescription=Google Ads Smile Rotator {campaign_id}\\n"
        f"After=network.target\\n\\n"
        f"[Service]\\nType=simple\\nWorkingDirectory=/opt/google-ads-rotator\\n"
        f"EnvironmentFile=/opt/google-ads-rotator/.env\\n"
        f"{env_line}"
        f"ExecStart=/opt/google-ads-rotator/venv/bin/python -m google_ads_mcp.rotator_smile {exec_args}\\n"
        f"Restart=always\\nRestartSec=30\\n"
        f"StandardOutput=append:/var/log/google-ads-smile-{campaign_id}.log\\n"
        f"StandardError=append:/var/log/google-ads-smile-{campaign_id}.log\\n\\n"
        f"[Install]\\nWantedBy=multi-user.target\\n'"
        f" > /etc/systemd/system/{svc}.service"
    )
    _ssh("systemctl daemon-reload")
    rc, out = _ssh(f"systemctl start {svc}")
    return {
        "status": "started" if rc == 0 else "error",
        "campaign_id": campaign_id,
        "customer_id": customer_id or "default",
        "interval": "20–30 мин",
        "mode": "smile (заголовки с эмодзи)",
        "log": f"/var/log/google-ads-smile-{campaign_id}.log",
        "detail": out or "ok",
    }


@mcp.tool()
def stop_smile_rotation(campaign_id: str) -> dict:
    """
    Остановить smile-ротацию для конкретной кампании на VPS.
    campaign_id — ID кампании.
    """
    svc = f"google-ads-smile-{campaign_id}"
    _, active = _ssh(f"systemctl is-active {svc}")

    if active.strip() == "active":
        _ssh(f"systemctl stop {svc}")
        _ssh(f"rm -f /etc/systemd/system/{svc}.service && systemctl daemon-reload")
        return {"status": "stopped", "campaign_id": campaign_id, "service": svc}

    return {"status": "not_running", "campaign_id": campaign_id}


@mcp.tool()
def rotation_status() -> dict:
    """Проверить статус ротации всех кампаний (обычной и smile) и последние строки логов с VPS."""
    _, services_main = _ssh(
        "systemctl list-units 'google-ads-rotator*' --no-legend --no-pager "
        "| awk '{print $1, $4}'"
    )
    _, services_smile = _ssh(
        "systemctl list-units 'google-ads-smile-*' --no-legend --no-pager "
        "| awk '{print $1, $4}'"
    )
    _, logs_main = _ssh(
        "for f in /var/log/google-ads-rotator-*.log; do "
        "echo \"=== $f ===\"; tail -2 $f 2>/dev/null; done"
    )
    _, logs_smile = _ssh(
        "for f in /var/log/google-ads-smile-*.log; do "
        "echo \"=== $f ===\"; tail -2 $f 2>/dev/null; done"
    )
    return {
        "main_rotation": services_main or "нет активных",
        "smile_rotation": services_smile or "нет активных",
        "logs_main": logs_main or "нет логов",
        "logs_smile": logs_smile or "нет логов",
    }


# ── Search Campaigns ───────────────────────────────────────────────────────

@mcp.tool()
def list_search_campaigns(status_filter: str = "ENABLED", customer_id: str = None) -> list[dict]:
    """
    Список поисковых кампаний (SEARCH).
    status_filter: ENABLED | PAUSED | ALL
    """
    return search.list_search_campaigns(get_client(), _cid(customer_id), status_filter)


# ── Ad Groups ──────────────────────────────────────────────────────────────

@mcp.tool()
def list_ad_groups(campaign_id: str, customer_id: str = None) -> list[dict]:
    """Список групп объявлений для кампании."""
    return search.list_ad_groups(get_client(), _cid(customer_id), campaign_id)


@mcp.tool()
def create_ad_group(
    campaign_id: str,
    name: str,
    cpc_bid_usd: float = None,
    ad_group_type: str = "SEARCH_STANDARD",
    customer_id: str = None,
) -> dict:
    """
    Создать группу объявлений в кампании.
    cpc_bid_usd — максимальная ставка за клик в USD (опционально).
    ad_group_type — тип группы:
      SEARCH_STANDARD (по умолчанию, для поисковых кампаний),
      пустая строка "" — для UAC/App кампаний (тип задаётся автоматически).
    Для App-кампаний: передай ad_group_type="" затем создай App Ad через create_app_ad.
    """
    return search.create_ad_group(get_client(), _cid(customer_id), campaign_id, name, cpc_bid_usd, ad_group_type or None)


# ── RSA Ads ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_rsa_ads(campaign_id: str, customer_id: str = None) -> list[dict]:
    """
    Список RSA-объявлений (Responsive Search Ads) кампании.
    Показывает заголовки, описания, URL, группу объявлений.
    """
    return search.list_rsa_ads(get_client(), _cid(customer_id), campaign_id)


@mcp.tool()
def create_rsa_ad(
    ad_group_id: str,
    headlines: list[str],
    descriptions: list[str],
    final_url: str,
    customer_id: str = None,
) -> dict:
    """
    Создать RSA-объявление (Responsive Search Ad).
    headlines: 3–15 заголовков (до 30 символов каждый).
    descriptions: 2–4 описания (до 90 символов каждое).
    final_url: целевая URL страница.
    """
    return search.create_rsa_ad(get_client(), _cid(customer_id), ad_group_id, headlines, descriptions, final_url)


@mcp.tool()
def update_rsa_ad(
    ad_id: str,
    ad_group_id: str,
    headlines: list[str],
    descriptions: list[str],
    final_url: str = None,
    customer_id: str = None,
) -> dict:
    """
    Обновить заголовки и описания RSA-объявления (полная замена).
    ad_id и ad_group_id — получи через list_rsa_ads.
    """
    return search.update_rsa_ad(get_client(), _cid(customer_id), ad_id, ad_group_id, headlines, descriptions, final_url)


# ── Keywords ───────────────────────────────────────────────────────────────

@mcp.tool()
def list_keywords(ad_group_id: str, customer_id: str = None) -> list[dict]:
    """
    Список ключевых слов в группе объявлений.
    Показывает текст, тип соответствия, ставку, Quality Score, статистику.
    """
    return search.list_keywords(get_client(), _cid(customer_id), ad_group_id)


@mcp.tool()
def add_keywords(
    ad_group_id: str,
    keywords: list[str],
    match_type: str,
    cpc_bid_usd: float = None,
    customer_id: str = None,
) -> list[dict]:
    """
    Добавить ключевые слова в группу объявлений.
    match_type: EXACT | PHRASE | BROAD
    cpc_bid_usd — ставка за клик в USD (опционально, иначе наследуется от группы).
    """
    return search.add_keywords(get_client(), _cid(customer_id), ad_group_id, keywords, match_type, cpc_bid_usd)


@mcp.tool()
def remove_keyword(
    ad_group_id: str,
    criterion_id: str,
    customer_id: str = None,
) -> dict:
    """
    Удалить ключевое слово из группы объявлений.
    criterion_id — получи через list_keywords.
    """
    return search.remove_keyword(get_client(), _cid(customer_id), ad_group_id, criterion_id)


# ── Negative Keywords ──────────────────────────────────────────────────────

@mcp.tool()
def list_negative_keywords(
    campaign_id: str = None,
    ad_group_id: str = None,
    customer_id: str = None,
) -> list[dict]:
    """
    Список минус-слов на уровне кампании или группы объявлений.
    Укажи campaign_id ИЛИ ad_group_id.
    """
    return search.list_negative_keywords(get_client(), _cid(customer_id), campaign_id, ad_group_id)


@mcp.tool()
def add_negative_keywords(
    keywords: list[str],
    match_type: str,
    campaign_id: str = None,
    ad_group_id: str = None,
    customer_id: str = None,
) -> list[dict]:
    """
    Добавить минус-слова на уровне кампании или группы объявлений.
    match_type: EXACT | PHRASE | BROAD
    Укажи campaign_id ИЛИ ad_group_id.
    """
    return search.add_negative_keywords(
        get_client(), _cid(customer_id), keywords, match_type, campaign_id, ad_group_id
    )


@mcp.tool()
def remove_negative_keyword(
    criterion_resource_name: str,
    customer_id: str = None,
) -> dict:
    """
    Удалить минус-слово по resource_name.
    resource_name — получи через list_negative_keywords (поле criterion_id нужно превратить в resource_name).
    Формат: customers/{customer_id}/campaignCriteria/{campaign_id}~{criterion_id}
    или: customers/{customer_id}/adGroupCriteria/{ad_group_id}~{criterion_id}
    """
    return search.remove_negative_keyword(get_client(), _cid(customer_id), criterion_resource_name)


# ── Search Stats ───────────────────────────────────────────────────────────

@mcp.tool()
def get_ad_group_metrics(
    campaign_id: str,
    date_range: str = "LAST_30_DAYS",
    customer_id: str = None,
) -> list[dict]:
    """
    Статистика по группам объявлений кампании.
    date_range: TODAY | LAST_7_DAYS | LAST_30_DAYS | THIS_MONTH | LAST_MONTH
    Возвращает impressions, clicks, conversions, cost, CTR, avg CPC — по каждой группе.
    """
    return search.get_ad_group_metrics(get_client(), _cid(customer_id), campaign_id, date_range)


@mcp.tool()
def get_rsa_ad_metrics(
    campaign_id: str,
    date_range: str = "LAST_30_DAYS",
    customer_id: str = None,
) -> list[dict]:
    """
    Статистика по RSA-объявлениям кампании.
    date_range: TODAY | LAST_7_DAYS | LAST_30_DAYS | THIS_MONTH | LAST_MONTH
    Возвращает impressions, clicks, conversions, cost, CTR — по каждому объявлению с заголовками.
    """
    return search.get_rsa_ad_metrics(get_client(), _cid(customer_id), campaign_id, date_range)


@mcp.tool()
def get_keyword_metrics(
    ad_group_id: str,
    date_range: str = "LAST_30_DAYS",
    customer_id: str = None,
) -> list[dict]:
    """
    Статистика по ключевым словам группы объявлений с фильтром по периоду.
    date_range: TODAY | LAST_7_DAYS | LAST_30_DAYS | THIS_MONTH | LAST_MONTH
    Возвращает impressions, clicks, conversions, cost, CTR, Quality Score — по каждому ключу.
    """
    return search.get_keyword_metrics(get_client(), _cid(customer_id), ad_group_id, date_range)


# ── HTML5 Banners ───────────────────────────────────────────────────────────

@mcp.tool()
def upload_html5_banner(
    file_path: str,
    ad_id: str,
    name: str = None,
    customer_id: str = None,
) -> dict:
    """
    Загрузить HTML5 ZIP-баннер и добавить к существующему App Ad.
    file_path — полный путь к ZIP-файлу на локальной машине.
    ad_id — ID объявления (получи через list_ad_group_ads).
    name — опционально, название ассета.
    """
    return assets.upload_html5_banner(get_client(), _cid(customer_id), file_path, ad_id, name)


@mcp.tool()
def list_html5_banners(campaign_id: str, customer_id: str = None) -> list[dict]:
    """
    Список HTML5 баннеров (media bundle assets) в App Ads кампании.
    Показывает какие ZIP-баннеры привязаны к каким объявлениям.
    """
    return assets.list_html5_banners(get_client(), _cid(customer_id), campaign_id)


# ── Geo Targeting ───────────────────────────────────────────────────────────

@mcp.tool()
def search_locations(query: str) -> list[dict]:
    """
    Найти страны/регионы/города для гео-таргетинга по названию.
    Возвращает id, name, country_code, target_type.
    Используй id из результата в add_campaign_locations.
    Примеры: "United States", "Germany", "California", "London"
    """
    return geo.search_geo_targets(get_client(), query)


@mcp.tool()
def list_campaign_locations(campaign_id: str, customer_id: str = None) -> list[dict]:
    """
    Список гео-таргетов кампании (страны, регионы).
    Показывает criterion_id, название, country_code, негативный ли таргет.
    criterion_id нужен для удаления через remove_campaign_location.
    """
    return geo.list_campaign_locations(get_client(), _cid(customer_id), campaign_id)


@mcp.tool()
def add_campaign_locations(
    campaign_id: str,
    geo_target_ids: list[str],
    negative: bool = False,
    customer_id: str = None,
) -> list[dict]:
    """
    Добавить страны/регионы к кампании.
    geo_target_ids — список ID из search_locations (поле "id").
    negative=true — добавить как исключение (exclude).
    Пример: geo_target_ids=["2840"] для США, ["2276"] для Германии.
    """
    return geo.add_campaign_locations(get_client(), _cid(customer_id), campaign_id, geo_target_ids, negative)


@mcp.tool()
def remove_campaign_location(
    campaign_id: str,
    criterion_id: str,
    customer_id: str = None,
) -> dict:
    """
    Удалить страну/регион из гео-таргетинга кампании.
    criterion_id — получи через list_campaign_locations.
    """
    return geo.remove_campaign_location(get_client(), _cid(customer_id), campaign_id, criterion_id)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
