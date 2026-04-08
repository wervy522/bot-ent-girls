import os
from functools import lru_cache
from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient

load_dotenv()


def _build_config() -> dict:
    return {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "use_proto_plus": True,
    }


@lru_cache(maxsize=1)
def get_client() -> GoogleAdsClient:
    config = _build_config()
    login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if login_customer_id:
        config["login_customer_id"] = login_customer_id
    return GoogleAdsClient.load_from_dict(config)


def get_customer_id() -> str:
    return os.environ["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")
