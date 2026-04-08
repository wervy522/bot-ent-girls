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
