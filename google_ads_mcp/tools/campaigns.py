from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2


def list_campaigns(client: GoogleAdsClient, customer_id: str, status_filter: str) -> list[dict]:
    ga_service = client.get_service("GoogleAdsService")

    where_clause = ""
    if status_filter != "ALL":
        where_clause = f"AND campaign.status = '{status_filter}'"

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign.app_campaign_setting.app_id,
            campaign.app_campaign_setting.app_store,
            campaign_budget.amount_micros
        FROM campaign
        WHERE campaign.advertising_channel_type = 'MULTI_CHANNEL'
          {where_clause}
        ORDER BY campaign.name
    """

    response = ga_service.search(customer_id=customer_id, query=query)
    result = []
    for row in response:
        c = row.campaign
        result.append({
            "id": str(c.id),
            "name": c.name,
            "status": c.status.name,
            "app_id": c.app_campaign_setting.app_id,
            "app_store": c.app_campaign_setting.app_store.name,
            "budget_micros": row.campaign_budget.amount_micros,
            "budget_usd": row.campaign_budget.amount_micros / 1_000_000,
        })
    return result


def get_campaign(client: GoogleAdsClient, customer_id: str, campaign_id: str) -> dict:
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.start_date,
            campaign.end_date,
            campaign.advertising_channel_type,
            campaign.app_campaign_setting.app_id,
            campaign.app_campaign_setting.app_store,
            campaign.app_campaign_setting.bidding_strategy_goal_type,
            campaign_budget.amount_micros,
            campaign.target_cpa.target_cpa_micros
        FROM campaign
        WHERE campaign.id = {campaign_id}
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    for row in response:
        c = row.campaign
        return {
            "id": str(c.id),
            "name": c.name,
            "status": c.status.name,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "app_id": c.app_campaign_setting.app_id,
            "app_store": c.app_campaign_setting.app_store.name,
            "bidding_goal": c.app_campaign_setting.bidding_strategy_goal_type.name,
            "budget_micros": row.campaign_budget.amount_micros,
            "budget_usd": row.campaign_budget.amount_micros / 1_000_000,
            "target_cpa_micros": c.target_cpa.target_cpa_micros,
            "target_cpa_usd": c.target_cpa.target_cpa_micros / 1_000_000,
        }
    raise ValueError(f"Campaign {campaign_id} not found")


def update_campaign_status(
    client: GoogleAdsClient, customer_id: str, campaign_id: str, status: str
) -> dict:
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")

    campaign = campaign_operation.update
    campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)

    status_enum = client.enums.CampaignStatusEnum[status]
    campaign.status = status_enum

    field_mask = field_mask_pb2.FieldMask(paths=["status"])
    campaign_operation.update_mask.CopyFrom(field_mask)

    response = campaign_service.mutate_campaigns(
        customer_id=customer_id,
        operations=[campaign_operation],
    )
    return {"updated": response.results[0].resource_name, "status": status}


def get_campaign_metrics(
    client: GoogleAdsClient, customer_id: str, campaign_id: str, date_range: str
) -> dict:
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.cost_micros,
            metrics.ctr,
            metrics.average_cpc
        FROM campaign
        WHERE campaign.id = {campaign_id}
          AND segments.date DURING {date_range}
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    for row in response:
        m = row.metrics
        return {
            "campaign_id": campaign_id,
            "date_range": date_range,
            "impressions": m.impressions,
            "clicks": m.clicks,
            "conversions": m.conversions,
            "cost_usd": m.cost_micros / 1_000_000,
            "ctr": round(m.ctr * 100, 2),
            "avg_cpc_usd": m.average_cpc / 1_000_000,
        }
    return {"campaign_id": campaign_id, "date_range": date_range, "impressions": 0}


# ── Создание кампаний ──────────────────────────────────────────────────────

def _create_budget(
    client: GoogleAdsClient,
    customer_id: str,
    budget_usd: float,
    name: str,
    shared: bool = False,
) -> str:
    """Создать бюджет кампании, вернуть resource_name."""
    budget_service = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    budget = op.create
    budget.name = name
    budget.amount_micros = int(budget_usd * 1_000_000)
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    if not shared:
        budget.explicitly_shared = False
    response = budget_service.mutate_campaign_budgets(
        customer_id=customer_id, operations=[op]
    )
    return response.results[0].resource_name


def create_search_campaign(
    client: GoogleAdsClient,
    customer_id: str,
    name: str,
    budget_usd: float,
    bidding_strategy: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_usd: float = None,
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """
    Создать поисковую кампанию.
    bidding_strategy: MAXIMIZE_CONVERSIONS | TARGET_CPA | MANUAL_CPC | MAXIMIZE_CONVERSION_VALUE
    start_date / end_date: формат YYYYMMDD (опционально).
    """
    budget_resource = _create_budget(client, customer_id, budget_usd, f"{name} Budget")

    campaign_service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    c = op.create
    c.name = name
    c.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    c.status = client.enums.CampaignStatusEnum.PAUSED  # создаём на паузе
    c.campaign_budget = budget_resource

    # Сетевые настройки
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = True
    c.network_settings.target_content_network = False

    # Стратегия ставок
    if bidding_strategy == "MAXIMIZE_CONVERSIONS":
        c.maximize_conversions.target_cpa_micros = (
            int(target_cpa_usd * 1_000_000) if target_cpa_usd else 0
        )
    elif bidding_strategy == "TARGET_CPA":
        c.target_cpa.target_cpa_micros = int((target_cpa_usd or 1) * 1_000_000)
    elif bidding_strategy == "MAXIMIZE_CONVERSION_VALUE":
        c.maximize_conversion_value.target_roas = 0
    elif bidding_strategy == "MANUAL_CPC":
        c.manual_cpc.enhanced_cpc_enabled = True

    if start_date:
        c.start_date = start_date
    if end_date:
        c.end_date = end_date

    response = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[op]
    )
    resource_name = response.results[0].resource_name
    campaign_id = resource_name.split("/")[-1]
    return {
        "campaign_id": campaign_id,
        "resource_name": resource_name,
        "name": name,
        "type": "SEARCH",
        "budget_usd": budget_usd,
        "bidding_strategy": bidding_strategy,
        "status": "PAUSED",
    }


def create_app_campaign(
    client: GoogleAdsClient,
    customer_id: str,
    name: str,
    app_id: str,
    app_store: str,
    budget_usd: float,
    bidding_goal: str = "OPTIMIZE_INSTALLS_TARGET_INSTALL_COST",
    target_cpa_usd: float = None,
    start_date: str = None,
) -> dict:
    """
    Создать UAC (App) кампанию.
    app_store: APPLE_APP_STORE | GOOGLE_APP_STORE
    bidding_goal:
      OPTIMIZE_INSTALLS_TARGET_INSTALL_COST — целевая цена за установку
      OPTIMIZE_IN_APP_CONVERSIONS_TARGET_INSTALL_COST — конверсии в приложении
      OPTIMIZE_IN_APP_CONVERSIONS_TARGET_CONVERSION_COST — целевая цена за конверсию
      OPTIMIZE_RETURN_ON_ADVERTISING_SPEND — ROAS
    target_cpa_usd — целевая цена (если применимо).
    """
    budget_resource = _create_budget(client, customer_id, budget_usd, f"{name} Budget")

    campaign_service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    c = op.create
    c.name = name
    c.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.MULTI_CHANNEL
    c.advertising_channel_sub_type = (
        client.enums.AdvertisingChannelSubTypeEnum.APP_CAMPAIGN
    )
    c.status = client.enums.CampaignStatusEnum.PAUSED
    c.campaign_budget = budget_resource

    # App настройки
    c.app_campaign_setting.app_id = app_id
    c.app_campaign_setting.app_store = client.enums.AppCampaignAppStoreEnum[app_store]
    c.app_campaign_setting.bidding_strategy_goal_type = (
        client.enums.AppCampaignBiddingStrategyGoalTypeEnum[bidding_goal]
    )

    # Стратегия ставок
    if target_cpa_usd is not None:
        c.target_cpa.target_cpa_micros = int(target_cpa_usd * 1_000_000)
    else:
        c.maximize_conversions.target_cpa_micros = 0

    if start_date:
        c.start_date = start_date

    response = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[op]
    )
    resource_name = response.results[0].resource_name
    campaign_id = resource_name.split("/")[-1]
    return {
        "campaign_id": campaign_id,
        "resource_name": resource_name,
        "name": name,
        "type": "APP",
        "app_id": app_id,
        "app_store": app_store,
        "budget_usd": budget_usd,
        "bidding_goal": bidding_goal,
        "target_cpa_usd": target_cpa_usd,
        "status": "PAUSED",
    }
