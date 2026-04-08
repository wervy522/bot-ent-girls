from google.ads.googleads.client import GoogleAdsClient
from google.protobuf import field_mask_pb2

# field_type -> FieldType enum name
FIELD_TYPE_MAP = {
    "HEADLINE": "HEADLINE",
    "DESCRIPTION": "DESCRIPTION",
    "LONG_HEADLINE": "LONG_HEADLINE",
}


def list_asset_groups(client: GoogleAdsClient, customer_id: str, campaign_id: str) -> list[dict]:
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            asset_group.id,
            asset_group.name,
            asset_group.status,
            asset_group.resource_name
        FROM asset_group
        WHERE asset_group.campaign = 'customers/{customer_id}/campaigns/{campaign_id}'
    """
    response = ga_service.search(customer_id=customer_id, query=query)
    result = []
    for row in response:
        ag = row.asset_group
        result.append({
            "id": str(ag.id),
            "name": ag.name,
            "status": ag.status.name,
            "resource_name": ag.resource_name,
        })
    return result


def get_asset_group(client: GoogleAdsClient, customer_id: str, asset_group_id: str) -> dict:
    ga_service = client.get_service("GoogleAdsService")

    resource_name = f"customers/{customer_id}/assetGroups/{asset_group_id}"

    query = f"""
        SELECT
            asset_group_asset.asset,
            asset_group_asset.field_type,
            asset_group_asset.resource_name,
            asset.id,
            asset.type,
            asset.text_asset.text,
            asset.name
        FROM asset_group_asset
        WHERE asset_group_asset.asset_group = '{resource_name}'
    """
    response = ga_service.search(customer_id=customer_id, query=query)

    assets_by_type: dict[str, list] = {}
    for row in response:
        aga = row.asset_group_asset
        asset = row.asset
        field_type = aga.field_type.name

        entry = {
            "asset_id": str(asset.id),
            "asset_group_asset_resource_name": aga.resource_name,
            "type": asset.type_.name,
            "text": asset.text_asset.text if asset.text_asset.text else None,
            "name": asset.name,
        }
        assets_by_type.setdefault(field_type, []).append(entry)

    return {
        "asset_group_id": asset_group_id,
        "assets": assets_by_type,
    }


def add_text_asset(
    client: GoogleAdsClient,
    customer_id: str,
    asset_group_id: str,
    text: str,
    field_type: str,
) -> dict:
    if field_type not in FIELD_TYPE_MAP:
        raise ValueError(f"field_type must be one of {list(FIELD_TYPE_MAP)}")

    asset_service = client.get_service("AssetService")
    asset_group_asset_service = client.get_service("AssetGroupAssetService")

    # 1. Create the text asset
    asset_operation = client.get_type("AssetOperation")
    new_asset = asset_operation.create
    new_asset.text_asset.text = text

    asset_response = asset_service.mutate_assets(
        customer_id=customer_id,
        operations=[asset_operation],
    )
    asset_resource_name = asset_response.results[0].resource_name

    # 2. Link asset to asset group
    aga_operation = client.get_type("AssetGroupAssetOperation")
    aga = aga_operation.create
    aga.asset_group = f"customers/{customer_id}/assetGroups/{asset_group_id}"
    aga.asset = asset_resource_name
    aga.field_type = client.enums.AssetFieldTypeEnum.AssetFieldType[
        FIELD_TYPE_MAP[field_type]
    ]

    aga_response = asset_group_asset_service.mutate_asset_group_assets(
        customer_id=customer_id,
        operations=[aga_operation],
    )

    return {
        "asset_resource_name": asset_resource_name,
        "asset_group_asset_resource_name": aga_response.results[0].resource_name,
        "text": text,
        "field_type": field_type,
    }


def update_app_ad_texts(
    client: GoogleAdsClient,
    customer_id: str,
    ad_id: str,
    headlines: list[str],
    descriptions: list[str],
    exempt_policy_violations: bool = False,
) -> dict:
    """
    Заменить все заголовки и описания в App Ad.
    Принимает ровно 2 заголовка и 1 описание.
    exempt_policy_violations=True — для заголовков с эмодзи (обходит SYMBOLS policy).
    """
    if len(headlines) != 2:
        raise ValueError("Нужно ровно 2 заголовка")
    if len(descriptions) != 1:
        raise ValueError("Нужно ровно 1 описание")

    ad_service = client.get_service("AdService")
    ad_operation = client.get_type("AdOperation")

    ad = ad_operation.update
    ad.resource_name = f"customers/{customer_id}/ads/{ad_id}"

    def make_asset(text: str):
        a = client.get_type("AdTextAsset")
        a.text = text
        return a

    ad.app_ad.headlines[:] = [make_asset(t) for t in headlines]
    ad.app_ad.descriptions[:] = [make_asset(t) for t in descriptions]

    field_mask = field_mask_pb2.FieldMask(paths=["app_ad.headlines", "app_ad.descriptions"])
    ad_operation.update_mask.CopyFrom(field_mask)

    if exempt_policy_violations:
        ad_operation.policy_validation_parameter.ignorable_policy_topics.append("SYMBOLS")

    response = ad_service.mutate_ads(customer_id=customer_id, operations=[ad_operation])
    return {
        "updated": response.results[0].resource_name,
        "headlines": headlines,
        "descriptions": descriptions,
    }


def list_ad_group_ads(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
) -> list[dict]:
    """Список всех App Ads с их ad_id и ad_group по кампании."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            ad_group_ad.ad.id,
            ad_group_ad.ad.name,
            ad_group_ad.status,
            ad_group.id,
            ad_group.name,
            ad_group_ad.ad.app_ad.headlines,
            ad_group_ad.ad.app_ad.descriptions
        FROM ad_group_ad
        WHERE campaign.id = {campaign_id}
          AND ad_group_ad.ad.type = 'APP_AD'
    """
    rows = list(ga_service.search(customer_id=customer_id, query=query))
    result = []
    for row in rows:
        result.append({
            "ad_id": str(row.ad_group_ad.ad.id),
            "ad_group_id": str(row.ad_group.id),
            "ad_group_name": row.ad_group.name,
            "status": row.ad_group_ad.status.name,
            "headlines": [h.text for h in row.ad_group_ad.ad.app_ad.headlines],
            "descriptions": [d.text for d in row.ad_group_ad.ad.app_ad.descriptions],
        })
    return result


def upload_html5_banner(
    client: GoogleAdsClient,
    customer_id: str,
    file_path: str,
    ad_id: str,
    name: str = None,
) -> dict:
    """
    Загрузить HTML5 ZIP-баннер и добавить к существующему App Ad.
    file_path — путь к ZIP-файлу на локальной машине.
    ad_id — получи через list_ad_group_ads.
    """
    with open(file_path, "rb") as f:
        data = f.read()

    # 1. Загружаем ZIP как MediaBundleAsset
    asset_service = client.get_service("AssetService")
    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create
    if name:
        asset.name = name
    else:
        import os
        asset.name = os.path.basename(file_path)
    asset.media_bundle_asset.data = data

    asset_response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_op]
    )
    asset_resource_name = asset_response.results[0].resource_name

    # 2. Добавляем к App Ad
    ad_service = client.get_service("AdService")
    ad_op = client.get_type("AdOperation")
    ad = ad_op.update
    ad.resource_name = f"customers/{customer_id}/ads/{ad_id}"

    bundle_asset = client.get_type("AdMediaBundleAsset")
    bundle_asset.asset = asset_resource_name
    ad.app_ad.html5_media_bundles.append(bundle_asset)

    field_mask = field_mask_pb2.FieldMask(paths=["app_ad.html5_media_bundles"])
    ad_op.update_mask.CopyFrom(field_mask)

    ad_response = ad_service.mutate_ads(customer_id=customer_id, operations=[ad_op])
    return {
        "asset_resource_name": asset_resource_name,
        "ad_updated": ad_response.results[0].resource_name,
        "file": file_path,
        "name": asset.name,
    }


def list_html5_banners(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
) -> list[dict]:
    """Список HTML5 баннеров (media bundle assets) в App Ads кампании."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            ad_group_ad.ad.id,
            ad_group_ad.ad.app_ad.html5_media_bundles,
            ad_group.id,
            ad_group.name
        FROM ad_group_ad
        WHERE campaign.id = {campaign_id}
          AND ad_group_ad.ad.type = 'APP_AD'
    """
    rows = list(ga_service.search(customer_id=customer_id, query=query))
    result = []
    for row in rows:
        bundles = row.ad_group_ad.ad.app_ad.html5_media_bundles
        if bundles:
            result.append({
                "ad_id": str(row.ad_group_ad.ad.id),
                "ad_group_id": str(row.ad_group.id),
                "ad_group_name": row.ad_group.name,
                "html5_bundles": [b.asset for b in bundles],
                "bundle_count": len(bundles),
            })
    return result


def remove_text_asset(
    client: GoogleAdsClient,
    customer_id: str,
    asset_group_asset_resource_name: str,
) -> dict:
    asset_group_asset_service = client.get_service("AssetGroupAssetService")

    aga_operation = client.get_type("AssetGroupAssetOperation")
    aga_operation.remove = asset_group_asset_resource_name

    asset_group_asset_service.mutate_asset_group_assets(
        customer_id=customer_id,
        operations=[aga_operation],
    )

    return {"removed": asset_group_asset_resource_name}
