"""
Инструменты для управления гео-таргетингом кампаний.
Добавление/удаление стран и регионов.
"""
from google.ads.googleads.client import GoogleAdsClient


def search_geo_targets(client: GoogleAdsClient, query_text: str) -> list[dict]:
    """Поиск гео-таргетов по названию (страны, регионы, города)."""
    geo_service = client.get_service("GeoTargetConstantService")
    request = client.get_type("SuggestGeoTargetConstantsRequest")
    request.locale = "en"
    request.search_term.value = query_text

    response = geo_service.suggest_geo_target_constants(request=request)
    result = []
    for suggestion in response.geo_target_constant_suggestions:
        geo = suggestion.geo_target_constant
        result.append({
            "id": str(geo.id),
            "resource_name": geo.resource_name,
            "name": geo.name,
            "country_code": geo.country_code,
            "target_type": geo.target_type.name,
            "canonical_name": suggestion.search_term,
        })
    return result


def list_campaign_locations(
    client: GoogleAdsClient, customer_id: str, campaign_id: str
) -> list[dict]:
    """Список гео-таргетов кампании (страны, регионы)."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            campaign_criterion.criterion_id,
            campaign_criterion.location.geo_target_constant,
            campaign_criterion.negative,
            campaign_criterion.status
        FROM campaign_criterion
        WHERE campaign.id = {campaign_id}
          AND campaign_criterion.type = 'LOCATION'
        ORDER BY campaign_criterion.criterion_id
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    return [
        {
            "criterion_id": str(row.campaign_criterion.criterion_id),
            "geo_target_resource": row.campaign_criterion.location.geo_target_constant,
            "negative": row.campaign_criterion.negative,
            "status": row.campaign_criterion.status.name,
        }
        for row in response
    ]


def add_campaign_locations(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
    geo_target_ids: list[str],
    negative: bool = False,
) -> list[dict]:
    """
    Добавить гео-таргеты к кампании по ID (из search_geo_targets).
    negative=True — добавить как исключение.
    """
    campaign_criterion_service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")
    geo_service = client.get_service("GeoTargetConstantService")

    operations = []
    for geo_id in geo_target_ids:
        op = client.get_type("CampaignCriterionOperation")
        cc = op.create
        cc.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        cc.negative = negative
        cc.location.geo_target_constant = geo_service.geo_target_constant_path(geo_id)
        operations.append(op)

    response = campaign_criterion_service.mutate_campaign_criteria(
        customer_id=customer_id, operations=operations
    )
    return [
        {"geo_target_id": gid, "resource_name": r.resource_name}
        for gid, r in zip(geo_target_ids, response.results)
    ]


def remove_campaign_location(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
    criterion_id: str,
) -> dict:
    """Удалить гео-таргет из кампании по criterion_id (из list_campaign_locations)."""
    campaign_criterion_service = client.get_service("CampaignCriterionService")
    resource_name = campaign_criterion_service.campaign_criterion_path(
        customer_id, campaign_id, criterion_id
    )
    op = client.get_type("CampaignCriterionOperation")
    op.remove = resource_name
    response = campaign_criterion_service.mutate_campaign_criteria(
        customer_id=customer_id, operations=[op]
    )
    return {"removed": response.results[0].resource_name}
