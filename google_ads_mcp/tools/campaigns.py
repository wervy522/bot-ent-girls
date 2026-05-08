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


# ── Конверсии ─────────────────────────────────────────────────────────────

def list_conversion_actions(
    client: GoogleAdsClient,
    customer_id: str,
    status_filter: str = "ENABLED",
) -> list[dict]:
    """Список конверсий аккаунта. status_filter: ENABLED | ALL."""
    ga_service = client.get_service("GoogleAdsService")
    where = f"WHERE conversion_action.status = '{status_filter}'" if status_filter != "ALL" else ""
    query = f"""
        SELECT
            conversion_action.id,
            conversion_action.name,
            conversion_action.status,
            conversion_action.type,
            conversion_action.category,
            conversion_action.include_in_conversions_metric
        FROM conversion_action
        {where}
        ORDER BY conversion_action.name
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    return [
        {
            "id": str(row.conversion_action.id),
            "name": row.conversion_action.name,
            "status": row.conversion_action.status.name,
            "type": row.conversion_action.type_.name,
            "category": row.conversion_action.category.name,
            "include_in_conversions": row.conversion_action.include_in_conversions_metric,
        }
        for row in response
    ]


def _auto_conversion_ids(client: GoogleAdsClient, customer_id: str) -> list[str]:
    """Вернуть ID всех ENABLED конверсий для selective_optimization."""
    actions = list_conversion_actions(client, customer_id, status_filter="ENABLED")
    if not actions:
        raise ValueError(
            f"В аккаунте {customer_id} нет активных конверсий. "
            "Создайте конверсию в Google Ads UI или передайте conversion_action_ids вручную."
        )
    return [a["id"] for a in actions]


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
    c.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )

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
    conversion_action_ids: list[str] = None,
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
    conversion_action_ids — список ID конверсий (обязателен для OPTIMIZE_IN_APP_CONVERSIONS_TARGET_CONVERSION_COST).
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

    # Обязательное поле — не политическая реклама (enum, не bool!)
    c.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )

    # App настройки
    c.app_campaign_setting.app_id = app_id
    c.app_campaign_setting.app_store = client.enums.AppCampaignAppStoreEnum[app_store]
    c.app_campaign_setting.bidding_strategy_goal_type = (
        client.enums.AppCampaignBiddingStrategyGoalTypeEnum[bidding_goal]
    )

    # Selective optimization — обязательно для OPTIMIZE_IN_APP_CONVERSIONS_TARGET_CONVERSION_COST
    # Если IDs не переданы явно — подтягиваем автоматически из аккаунта
    _GOALS_REQUIRING_CONVERSIONS = {
        "OPTIMIZE_IN_APP_CONVERSIONS_TARGET_CONVERSION_COST",
        "OPTIMIZE_IN_APP_CONVERSIONS_TARGET_INSTALL_COST",
    }
    if conversion_action_ids is None and bidding_goal in _GOALS_REQUIRING_CONVERSIONS:
        conversion_action_ids = _auto_conversion_ids(client, customer_id)

    if conversion_action_ids:
        conversion_action_service = client.get_service("ConversionActionService")
        for ca_id in conversion_action_ids:
            ca_resource = conversion_action_service.conversion_action_path(
                customer_id, ca_id
            )
            c.selective_optimization.conversion_actions.append(ca_resource)

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
        "conversion_action_ids": conversion_action_ids or [],
        "status": "PAUSED",
    }
