"""
Инструменты для работы с поисковыми кампаниями (SEARCH).
Группы объявлений, RSA-объявления, ключевые слова, минус-слова.
"""
from google.ads.googleads.client import GoogleAdsClient
from google.protobuf import field_mask_pb2


# ── Кампании ───────────────────────────────────────────────────────────────

def list_search_campaigns(client: GoogleAdsClient, customer_id: str, status_filter: str) -> list[dict]:
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
            campaign_budget.amount_micros
        FROM campaign
        WHERE campaign.advertising_channel_type = 'SEARCH'
          {where_clause}
        ORDER BY campaign.name
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    return [
        {
            "id": str(row.campaign.id),
            "name": row.campaign.name,
            "status": row.campaign.status.name,
            "budget_usd": row.campaign_budget.amount_micros / 1_000_000,
        }
        for row in response
    ]


# ── Группы объявлений ──────────────────────────────────────────────────────

def list_ad_groups(client: GoogleAdsClient, customer_id: str, campaign_id: str) -> list[dict]:
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status,
            ad_group.cpc_bid_micros
        FROM ad_group
        WHERE campaign.id = {campaign_id}
        ORDER BY ad_group.name
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    return [
        {
            "id": str(row.ad_group.id),
            "name": row.ad_group.name,
            "status": row.ad_group.status.name,
            "cpc_bid_usd": row.ad_group.cpc_bid_micros / 1_000_000,
        }
        for row in response
    ]


def create_ad_group(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
    name: str,
    cpc_bid_usd: float = None,
    ad_group_type: str = "SEARCH_STANDARD",
) -> dict:
    ad_group_service = client.get_service("AdGroupService")
    campaign_service = client.get_service("CampaignService")

    ad_group_operation = client.get_type("AdGroupOperation")
    ag = ad_group_operation.create
    ag.name = name
    ag.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    ag.status = client.enums.AdGroupStatusEnum.ENABLED
    if ad_group_type:
        ag.type_ = client.enums.AdGroupTypeEnum[ad_group_type]
    if cpc_bid_usd is not None:
        ag.cpc_bid_micros = int(cpc_bid_usd * 1_000_000)

    response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id,
        operations=[ad_group_operation],
    )
    resource_name = response.results[0].resource_name
    ad_group_id = resource_name.split("/")[-1]
    return {"ad_group_id": ad_group_id, "resource_name": resource_name, "name": name}


# ── RSA объявления ─────────────────────────────────────────────────────────

def list_rsa_ads(client: GoogleAdsClient, customer_id: str, campaign_id: str) -> list[dict]:
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            ad_group_ad.ad.id,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions,
            ad_group_ad.ad.final_urls,
            ad_group_ad.status,
            ad_group.id,
            ad_group.name
        FROM ad_group_ad
        WHERE campaign.id = {campaign_id}
          AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
        ORDER BY ad_group.name
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    result = []
    for row in response:
        ad = row.ad_group_ad.ad
        rsa = ad.responsive_search_ad
        result.append({
            "ad_id": str(ad.id),
            "ad_group_id": str(row.ad_group.id),
            "ad_group_name": row.ad_group.name,
            "status": row.ad_group_ad.status.name,
            "final_url": ad.final_urls[0] if ad.final_urls else "",
            "headlines": [h.text for h in rsa.headlines],
            "descriptions": [d.text for d in rsa.descriptions],
        })
    return result


def create_rsa_ad(
    client: GoogleAdsClient,
    customer_id: str,
    ad_group_id: str,
    headlines: list[str],
    descriptions: list[str],
    final_url: str,
) -> dict:
    """Создать RSA объявление. 3-15 заголовков (до 30 символов), 2-4 описания (до 90 символов)."""
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_group_service = client.get_service("AdGroupService")

    ad_group_ad_operation = client.get_type("AdGroupAdOperation")
    aga = ad_group_ad_operation.create
    aga.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED

    ad = aga.ad
    ad.final_urls.append(final_url)

    rsa = ad.responsive_search_ad
    for text in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = text[:30]
        rsa.headlines.append(asset)
    for text in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = text[:90]
        rsa.descriptions.append(asset)

    response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id,
        operations=[ad_group_ad_operation],
    )
    resource_name = response.results[0].resource_name
    ad_id = resource_name.split("~")[-1]
    return {"ad_id": ad_id, "resource_name": resource_name}


def update_rsa_ad(
    client: GoogleAdsClient,
    customer_id: str,
    ad_id: str,
    ad_group_id: str,
    headlines: list[str],
    descriptions: list[str],
    final_url: str = None,
) -> dict:
    """Обновить заголовки и описания RSA объявления (полная замена)."""
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_group_service = client.get_service("AdGroupService")

    ad_group_ad_operation = client.get_type("AdGroupAdOperation")
    aga = ad_group_ad_operation.update
    aga.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)

    ad = aga.ad
    ad.resource_name = client.get_service("AdService").ad_path(customer_id, ad_id)

    if final_url:
        ad.final_urls.append(final_url)

    rsa = ad.responsive_search_ad
    for text in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = text[:30]
        rsa.headlines.append(asset)
    for text in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = text[:90]
        rsa.descriptions.append(asset)

    paths = ["ad.responsive_search_ad.headlines", "ad.responsive_search_ad.descriptions"]
    if final_url:
        paths.append("ad.final_urls")
    field_mask = field_mask_pb2.FieldMask(paths=paths)
    ad_group_ad_operation.update_mask.CopyFrom(field_mask)

    response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id,
        operations=[ad_group_ad_operation],
    )
    return {"updated": response.results[0].resource_name}


# ── Ключевые слова ─────────────────────────────────────────────────────────

def list_keywords(client: GoogleAdsClient, customer_id: str, ad_group_id: str) -> list[dict]:
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            ad_group_criterion.criterion_id,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.cpc_bid_micros,
            ad_group_criterion.quality_info.quality_score,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros
        FROM ad_group_criterion
        WHERE ad_group.id = {ad_group_id}
          AND ad_group_criterion.type = 'KEYWORD'
          AND ad_group_criterion.negative = FALSE
        ORDER BY ad_group_criterion.keyword.text
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    return [
        {
            "criterion_id": str(row.ad_group_criterion.criterion_id),
            "keyword": row.ad_group_criterion.keyword.text,
            "match_type": row.ad_group_criterion.keyword.match_type.name,
            "status": row.ad_group_criterion.status.name,
            "cpc_bid_usd": row.ad_group_criterion.cpc_bid_micros / 1_000_000,
            "quality_score": row.ad_group_criterion.quality_info.quality_score,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost_usd": row.metrics.cost_micros / 1_000_000,
        }
        for row in response
    ]


def add_keywords(
    client: GoogleAdsClient,
    customer_id: str,
    ad_group_id: str,
    keywords: list[str],
    match_type: str,
    cpc_bid_usd: float = None,
) -> list[dict]:
    """Добавить ключевые слова. match_type: EXACT | PHRASE | BROAD"""
    ad_group_criterion_service = client.get_service("AdGroupCriterionService")
    ad_group_service = client.get_service("AdGroupService")
    match_type_enum = client.enums.KeywordMatchTypeEnum[match_type]

    operations = []
    for kw in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        agc = op.create
        agc.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
        agc.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        agc.keyword.text = kw
        agc.keyword.match_type = match_type_enum
        if cpc_bid_usd is not None:
            agc.cpc_bid_micros = int(cpc_bid_usd * 1_000_000)
        operations.append(op)

    response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id,
        operations=operations,
    )
    return [
        {"keyword": kw, "resource_name": r.resource_name}
        for kw, r in zip(keywords, response.results)
    ]


def remove_keyword(
    client: GoogleAdsClient,
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
) -> dict:
    ad_group_criterion_service = client.get_service("AdGroupCriterionService")
    resource_name = ad_group_criterion_service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )
    op = client.get_type("AdGroupCriterionOperation")
    op.remove = resource_name
    response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=[op]
    )
    return {"removed": response.results[0].resource_name}


# ── Минус-слова ────────────────────────────────────────────────────────────

def list_negative_keywords(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str = None,
    ad_group_id: str = None,
) -> list[dict]:
    ga_service = client.get_service("GoogleAdsService")

    if campaign_id:
        query = f"""
            SELECT
                campaign_criterion.criterion_id,
                campaign_criterion.keyword.text,
                campaign_criterion.keyword.match_type
            FROM campaign_criterion
            WHERE campaign.id = {campaign_id}
              AND campaign_criterion.type = 'KEYWORD'
              AND campaign_criterion.negative = TRUE
            ORDER BY campaign_criterion.keyword.text
        """
        response = ga_service.search(customer_id=customer_id, query=query)
        return [
            {
                "criterion_id": str(row.campaign_criterion.criterion_id),
                "keyword": row.campaign_criterion.keyword.text,
                "match_type": row.campaign_criterion.keyword.match_type.name,
                "level": "campaign",
                "campaign_id": campaign_id,
            }
            for row in response
        ]
    elif ad_group_id:
        query = f"""
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type
            FROM ad_group_criterion
            WHERE ad_group.id = {ad_group_id}
              AND ad_group_criterion.type = 'KEYWORD'
              AND ad_group_criterion.negative = TRUE
            ORDER BY ad_group_criterion.keyword.text
        """
        response = ga_service.search(customer_id=customer_id, query=query)
        return [
            {
                "criterion_id": str(row.ad_group_criterion.criterion_id),
                "keyword": row.ad_group_criterion.keyword.text,
                "match_type": row.ad_group_criterion.keyword.match_type.name,
                "level": "ad_group",
                "ad_group_id": ad_group_id,
            }
            for row in response
        ]
    else:
        raise ValueError("Укажи campaign_id или ad_group_id")


def add_negative_keywords(
    client: GoogleAdsClient,
    customer_id: str,
    keywords: list[str],
    match_type: str,
    campaign_id: str = None,
    ad_group_id: str = None,
) -> list[dict]:
    """Добавить минус-слова на уровне кампании или группы объявлений."""
    match_type_enum = client.enums.KeywordMatchTypeEnum[match_type]

    if campaign_id:
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        campaign_service = client.get_service("CampaignService")
        operations = []
        for kw in keywords:
            op = client.get_type("CampaignCriterionOperation")
            cc = op.create
            cc.campaign = campaign_service.campaign_path(customer_id, campaign_id)
            cc.negative = True
            cc.keyword.text = kw
            cc.keyword.match_type = match_type_enum
            operations.append(op)
        response = campaign_criterion_service.mutate_campaign_criteria(
            customer_id=customer_id, operations=operations
        )
        return [
            {"keyword": kw, "resource_name": r.resource_name, "level": "campaign"}
            for kw, r in zip(keywords, response.results)
        ]
    elif ad_group_id:
        ad_group_criterion_service = client.get_service("AdGroupCriterionService")
        ad_group_service = client.get_service("AdGroupService")
        operations = []
        for kw in keywords:
            op = client.get_type("AdGroupCriterionOperation")
            agc = op.create
            agc.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
            agc.negative = True
            agc.keyword.text = kw
            agc.keyword.match_type = match_type_enum
            operations.append(op)
        response = ad_group_criterion_service.mutate_ad_group_criteria(
            customer_id=customer_id, operations=operations
        )
        return [
            {"keyword": kw, "resource_name": r.resource_name, "level": "ad_group"}
            for kw, r in zip(keywords, response.results)
        ]
    else:
        raise ValueError("Укажи campaign_id или ad_group_id")


def remove_negative_keyword(
    client: GoogleAdsClient,
    customer_id: str,
    criterion_resource_name: str,
) -> dict:
    """Удалить минус-слово по resource_name (из list_negative_keywords нет, но criterion_id есть)."""
    if "/campaignCriteria/" in criterion_resource_name:
        service = client.get_service("CampaignCriterionService")
        op = client.get_type("CampaignCriterionOperation")
        op.remove = criterion_resource_name
        response = service.mutate_campaign_criteria(
            customer_id=customer_id, operations=[op]
        )
    else:
        service = client.get_service("AdGroupCriterionService")
        op = client.get_type("AdGroupCriterionOperation")
        op.remove = criterion_resource_name
        response = service.mutate_ad_group_criteria(
            customer_id=customer_id, operations=[op]
        )
    return {"removed": response.results[0].resource_name}


# ── Статистика ─────────────────────────────────────────────────────────────

def get_ad_group_metrics(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
    date_range: str,
) -> list[dict]:
    """Статистика по группам объявлений кампании."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            ad_group.id,
            ad_group.name,
            ad_group.status,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.cost_micros,
            metrics.ctr,
            metrics.average_cpc,
            metrics.average_cpm,
            metrics.conversions_value
        FROM ad_group
        WHERE campaign.id = {campaign_id}
          AND segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    result = []
    for row in response:
        m = row.metrics
        result.append({
            "ad_group_id": str(row.ad_group.id),
            "ad_group_name": row.ad_group.name,
            "status": row.ad_group.status.name,
            "impressions": m.impressions,
            "clicks": m.clicks,
            "conversions": round(m.conversions, 2),
            "cost_usd": round(m.cost_micros / 1_000_000, 2),
            "ctr": round(m.ctr * 100, 2),
            "avg_cpc_usd": round(m.average_cpc / 1_000_000, 2),
            "avg_cpm_usd": round(m.average_cpm / 1_000_000, 2),
            "conversions_value": round(m.conversions_value, 2),
        })
    return result


def get_rsa_ad_metrics(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
    date_range: str,
) -> list[dict]:
    """Статистика по RSA-объявлениям кампании."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            ad_group_ad.ad.id,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions,
            ad_group_ad.status,
            ad_group.id,
            ad_group.name,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.cost_micros,
            metrics.ctr,
            metrics.average_cpc,
            metrics.conversions_value
        FROM ad_group_ad
        WHERE campaign.id = {campaign_id}
          AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
          AND segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    result = []
    for row in response:
        m = row.metrics
        ad = row.ad_group_ad.ad
        rsa = ad.responsive_search_ad
        result.append({
            "ad_id": str(ad.id),
            "ad_group_id": str(row.ad_group.id),
            "ad_group_name": row.ad_group.name,
            "status": row.ad_group_ad.status.name,
            "headlines": [h.text for h in rsa.headlines],
            "descriptions": [d.text for d in rsa.descriptions],
            "impressions": m.impressions,
            "clicks": m.clicks,
            "conversions": round(m.conversions, 2),
            "cost_usd": round(m.cost_micros / 1_000_000, 2),
            "ctr": round(m.ctr * 100, 2),
            "avg_cpc_usd": round(m.average_cpc / 1_000_000, 2),
            "conversions_value": round(m.conversions_value, 2),
        })
    return result


def get_keyword_metrics(
    client: GoogleAdsClient,
    customer_id: str,
    ad_group_id: str,
    date_range: str,
) -> list[dict]:
    """Статистика по ключевым словам группы объявлений с фильтром по периоду."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            ad_group_criterion.criterion_id,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.quality_info.quality_score,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.cost_micros,
            metrics.ctr,
            metrics.average_cpc,
            metrics.average_position,
            metrics.conversions_value
        FROM ad_group_criterion
        WHERE ad_group.id = {ad_group_id}
          AND ad_group_criterion.type = 'KEYWORD'
          AND ad_group_criterion.negative = FALSE
          AND segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    result = []
    for row in response:
        m = row.metrics
        kw = row.ad_group_criterion
        result.append({
            "criterion_id": str(kw.criterion_id),
            "keyword": kw.keyword.text,
            "match_type": kw.keyword.match_type.name,
            "status": kw.status.name,
            "quality_score": kw.quality_info.quality_score,
            "impressions": m.impressions,
            "clicks": m.clicks,
            "conversions": round(m.conversions, 2),
            "cost_usd": round(m.cost_micros / 1_000_000, 2),
            "ctr": round(m.ctr * 100, 2),
            "avg_cpc_usd": round(m.average_cpc / 1_000_000, 2),
            "conversions_value": round(m.conversions_value, 2),
        })
    return result
