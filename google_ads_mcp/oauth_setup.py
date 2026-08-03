"""
Получение refresh_token для дополнительного MCC под ДРУГИМ гугл-аккаунтом.

    python -m google_ads_mcp.oauth_setup NEW

Откроет браузер. Залогинься под тем аккаунтом, у которого есть доступ к нужному MCC.
Токен запишется в .env как GOOGLE_ADS_MCC_<ИМЯ>_REFRESH_TOKEN — в консоль не печатается.

OAuth-клиент по умолчанию берётся из дефолтной секции .env (тот же Google Cloud
проект → подходит уже одобренный GOOGLE_ADS_DEVELOPER_TOKEN). Если у MCC свой
Cloud-проект, заранее пропиши GOOGLE_ADS_MCC_<ИМЯ>_CLIENT_ID / _CLIENT_SECRET
и его собственный _DEVELOPER_TOKEN.
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/adwords"]
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _upsert_env(key: str, value: str) -> None:
    """Записать/обновить переменную в .env, не трогая остальное."""
    text = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    ENV_PATH.write_text(text)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    mcc = sys.argv[1].upper()
    load_dotenv(ENV_PATH)
    prefix = f"GOOGLE_ADS_MCC_{mcc}_"

    client_id = os.environ.get(f"{prefix}CLIENT_ID") or os.environ["GOOGLE_ADS_CLIENT_ID"]
    client_secret = (
        os.environ.get(f"{prefix}CLIENT_SECRET") or os.environ["GOOGLE_ADS_CLIENT_SECRET"]
    )
    login_cid = os.environ.get(f"{prefix}LOGIN_CUSTOMER_ID")
    if not login_cid:
        print(f"Сначала добавь в .env: {prefix}LOGIN_CUSTOMER_ID=<id нового MCC>")
        return 1

    print(f"MCC {mcc} (login_customer_id={login_cid})")
    print("Открываю браузер — войди под аккаунтом, у которого есть доступ к этому MCC.\n")

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="Открой ссылку, если браузер не запустился:\n{url}\n",
        success_message="Готово — вкладку можно закрыть.",
    )

    if not creds.refresh_token:
        print("Google не вернул refresh_token. Повтори запуск (нужен prompt=consent).")
        return 1

    _upsert_env(f"{prefix}REFRESH_TOKEN", creds.refresh_token)
    print(f"\nrefresh_token записан в .env → {prefix}REFRESH_TOKEN")
    print("Дальше: проверь доступ через list_accounts в MCP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
