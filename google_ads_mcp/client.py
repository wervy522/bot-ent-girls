"""
Клиенты Google Ads API с поддержкой нескольких MCC.

Дефолтный MCC берётся из GOOGLE_ADS_* переменных.
Дополнительные MCC объявляются через префикс GOOGLE_ADS_MCC_<ИМЯ>_*:
    GOOGLE_ADS_MCC_NEWMCC_DEVELOPER_TOKEN=...
    GOOGLE_ADS_MCC_NEWMCC_LOGIN_CUSTOMER_ID=...
    GOOGLE_ADS_MCC_NEWMCC_CLIENT_ID=...      # опционально
    GOOGLE_ADS_MCC_NEWMCC_CLIENT_SECRET=...  # опционально
    GOOGLE_ADS_MCC_NEWMCC_REFRESH_TOKEN=...  # опционально

OAuth-поля наследуются от дефолтного MCC, если не заданы явно.
"""
import os
import re
from functools import lru_cache
from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient

load_dotenv()

DEFAULT_MCC = "default"

_MCC_VAR_RE = re.compile(r"^GOOGLE_ADS_MCC_([A-Z0-9]+)_LOGIN_CUSTOMER_ID$")


def _default_oauth() -> dict:
    return {
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
    }


@lru_cache(maxsize=1)
def list_mccs() -> tuple[str, ...]:
    """Имена всех настроенных MCC. Первый — дефолтный."""
    extra = sorted(
        m.group(1).lower()
        for key in os.environ
        if (m := _MCC_VAR_RE.match(key))
    )
    return (DEFAULT_MCC, *extra)


def _mcc_config(mcc: str) -> dict:
    if mcc == DEFAULT_MCC:
        return {
            "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
            **_default_oauth(),
            "login_customer_id": os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", ""),
            "use_proto_plus": True,
        }

    prefix = f"GOOGLE_ADS_MCC_{mcc.upper()}_"
    login_cid = os.environ.get(f"{prefix}LOGIN_CUSTOMER_ID")
    if not login_cid:
        raise ValueError(
            f"MCC '{mcc}' не настроен. Добавь в .env: {prefix}DEVELOPER_TOKEN и {prefix}LOGIN_CUSTOMER_ID"
        )

    oauth = _default_oauth()
    for field in ("client_id", "client_secret", "refresh_token"):
        override = os.environ.get(f"{prefix}{field.upper()}")
        if override:
            oauth[field] = override

    return {
        "developer_token": os.environ.get(f"{prefix}DEVELOPER_TOKEN")
        or os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        **oauth,
        "login_customer_id": login_cid.replace("-", ""),
        "use_proto_plus": True,
    }


@lru_cache(maxsize=8)
def get_client(mcc: str = DEFAULT_MCC) -> GoogleAdsClient:
    config = _mcc_config(mcc)
    if not config["login_customer_id"]:
        config.pop("login_customer_id")
    return GoogleAdsClient.load_from_dict(config)


@lru_cache(maxsize=8)
def list_child_accounts(mcc: str = DEFAULT_MCC) -> tuple[dict, ...]:
    """Все клиентские аккаунты под указанным MCC."""
    client = get_client(mcc)
    ga_service = client.get_service("GoogleAdsService")
    login_cid = _mcc_config(mcc)["login_customer_id"]
    query = """
        SELECT
            customer_client.id,
            customer_client.descriptive_name,
            customer_client.manager,
            customer_client.status
        FROM customer_client
        WHERE customer_client.manager = FALSE
    """
    rows = ga_service.search(customer_id=login_cid, query=query)
    return tuple(
        {
            "id": str(r.customer_client.id),
            "name": r.customer_client.descriptive_name,
            "status": r.customer_client.status.name,
            "mcc": mcc,
        }
        for r in rows
    )


@lru_cache(maxsize=256)
def resolve_mcc(customer_id: str) -> str:
    """Найти MCC, под которым живёт аккаунт."""
    cid = customer_id.replace("-", "")
    for mcc in list_mccs():
        try:
            if any(a["id"] == cid for a in list_child_accounts(mcc)):
                return mcc
        except Exception:
            continue
    return DEFAULT_MCC


def client_for(customer_id: str = None) -> GoogleAdsClient:
    """Клиент с правильным MCC для указанного аккаунта."""
    if not customer_id:
        return get_client(DEFAULT_MCC)
    return get_client(resolve_mcc(customer_id))


def get_customer_id() -> str:
    return os.environ["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")
