# from typing import Dict, Any
# import requests


# def query_vds(api_key: str, datasource_luid: str, url: str, query: Dict[str, Any]) -> Dict[str, Any]:
#     full_url = f"{url}/api/v1/vizql-data-service/query-datasource"

#     payload = {
#         "datasource": {
#             "datasourceLuid": datasource_luid
#         },
#         "query": query
#     }

#     headers = {
#         'X-Tableau-Auth': api_key,
#         'Content-Type': 'application/json'
#     }

#     response = requests.post(full_url, headers=headers, json=payload)

#     if response.status_code == 200:
#         return response.json()
#     else:
#         error_message = (
#             f"Failed to query data source via Tableau VizQL Data Service. "
#             f"Status code: {response.status_code}. Response: {response.text}"
#         )
#         raise RuntimeError(error_message)


# def query_vds_metadata(api_key: str, datasource_luid: str, url: str) -> Dict[str, Any]:
#     full_url = f"{url}/api/v1/vizql-data-service/read-metadata"

#     payload = {
#         "datasource": {
#             "datasourceLuid": datasource_luid
#         }
#     }

#     headers = {
#         'X-Tableau-Auth': api_key,
#         'Content-Type': 'application/json'
#     }

#     response = requests.post(full_url, headers=headers, json=payload)

#     if response.status_code == 200:
#         return response.json()
#     else:
#         error_message = (
#             f"Failed to obtain data source metadata from VizQL Data Service. "
#             f"Status code: {response.status_code}. Response: {response.text}"
#         )
#         raise RuntimeError(error_message)

from typing import Dict, Any, List, Optional
import json
import requests


def _get_caption(col_obj: Dict[str, Any]) -> Optional[str]:
    """
    Extract a field caption/name from either:
      {"column": {"fieldCaption": "Sales"}}  or  {"fieldCaption": "Sales"}  forms.
    """
    if not isinstance(col_obj, dict):
        return None
    obj = col_obj.get("column", col_obj)
    return obj.get("fieldCaption") or obj.get("caption") or obj.get("name")


def _adapt_old_request_to_new_query(old_req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert the legacy request shape:
      { "columns": [...], "aggregation": {...}, "groupBy": [...], "orderBy": [...], "limit": N }
    into the new VDS 'query' shape:
      { "fields": [...], "filters": [...] }

    This handles the common pattern (1 dimension group-by, aggregated measures, sort+topN).
    """
    cols: List[Dict[str, Any]] = old_req.get("columns", []) or []
    agg: Dict[str, str] = old_req.get("aggregation", {}) or {}
    gb: List[Dict[str, Any]] = old_req.get("groupBy", []) or []
    ob: List[Dict[str, Any]] = old_req.get("orderBy", []) or []
    limit = old_req.get("limit", None)

    # Determine grouping dimension(s)
    dim_caps: List[str] = [_get_caption(g) for g in gb if _get_caption(g)] if gb else []
    if not dim_caps and cols:
        first_cap = _get_caption(cols[0])
        if first_cap:
            dim_caps = [first_cap]

    # Build fields list (dimension(s) first, then measures w/ aggregation)
    fields: List[Dict[str, Any]] = []
    for c in cols:
        cap = _get_caption(c)
        if not cap:
            continue
        if cap in dim_caps:
            fields.append({"fieldCaption": cap})
        else:
            f: Dict[str, Any] = {"fieldCaption": cap}
            fn = agg.get(cap)
            if fn:
                f["function"] = fn
            fields.append(f)

    # Apply first sort (if any) to the matching field
    if ob:
        first = ob[0]
        sort_cap = _get_caption(first)
        direction = first.get("direction", "DESC")
        for f in fields:
            if f.get("fieldCaption") == sort_cap:
                f["sortPriority"] = 1
                f["sortDirection"] = direction
                break

    # Translate "limit" into a TOP filter on the first dimension by the sorted measure
    filters: List[Dict[str, Any]] = []
    if limit and dim_caps:
        sort_meas = next((f for f in fields if f.get("sortPriority") == 1 and "function" in f), None)
        if sort_meas:
            filters.append({
                "field": {"fieldCaption": dim_caps[0]},
                "filterType": "TOP",
                "howMany": limit,
                "fieldToMeasure": {
                    "fieldCaption": sort_meas["fieldCaption"],
                    "function": sort_meas.get("function", "SUM"),
                },
                "direction": "TOP",
            })

    new_query: Dict[str, Any] = {"fields": fields}
    if filters:
        new_query["filters"] = filters
    return new_query


def query_vds(
    api_key: str,
    datasource_luid: str,
    url: str,
    query: Dict[str, Any],
    *,
    timeout: int = 60,
    debug: bool = True,
) -> Dict[str, Any]:
    """
    POST {url}/api/v1/vizql-data-service/query-datasource

    Accepts either:
      - a correct VDS 'query' dict with a 'fields' array, or
      - a legacy 'request' dict (columns/aggregation/groupBy/orderBy/limit), which will be adapted.
    """
    # Guard/adapter for shape
    if "fields" not in query:
        # If it looks like the legacy shape, adapt it
        if any(k in query for k in ("columns", "aggregation", "groupBy", "orderBy", "limit")):
            query = _adapt_old_request_to_new_query(query)
        else:
            raise ValueError(f"VDS query must include a 'fields' array. Got keys: {list(query.keys())}")

    full_url = f"{url}/api/v1/vizql-data-service/query-datasource"
    payload = {
        "datasource": {"datasourceLuid": datasource_luid},
        "query": query,
        "options": {"returnFormat": "OBJECTS", "debug": True, "disaggregate": False},
    }
    headers = {
        "X-Tableau-Auth": api_key,
        "Content-Type": "application/json",
    }

    if debug:
        print("DEBUG VDS BODY:", json.dumps(payload, indent=2)[:2000])

    response = requests.post(full_url, headers=headers, json=payload, timeout=timeout)

    if response.ok:
        return response.json()

    error_message = (
        "Failed to query data source via Tableau VizQL Data Service. "
        f"Status code: {response.status_code}. Response: {response.text}"
    )
    raise RuntimeError(error_message)


def query_vds_metadata(
    api_key: str,
    datasource_luid: str,
    url: str,
    *,
    timeout: int = 60,
    debug: bool = True,
) -> Dict[str, Any]:
    """
    POST {url}/api/v1/vizql-data-service/read-metadata
    """
    full_url = f"{url}/api/v1/vizql-data-service/read-metadata"
    payload = {
        "datasource": {"datasourceLuid": datasource_luid},
        "options": {"debug": True},
    }
    headers = {
        "X-Tableau-Auth": api_key,
        "Content-Type": "application/json",
    }

    if debug:
        print("DEBUG VDS METADATA BODY:", json.dumps(payload, indent=2))

    response = requests.post(full_url, headers=headers, json=payload, timeout=timeout)

    if response.ok:
        return response.json()

    error_message = (
        "Failed to obtain data source metadata from VizQL Data Service. "
        f"Status code: {response.status_code}. Response: {response.text}"
    )
    raise RuntimeError(error_message)
