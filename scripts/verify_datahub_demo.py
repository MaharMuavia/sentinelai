#!/usr/bin/env python3
"""Fail-closed acceptance test for the live DataHub MCP demo graph."""

from __future__ import annotations

import asyncio
import argparse
import logging
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.datahub.client import DataHubClient, IntegrationMode

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("sentinel.verify")

RAW = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
CUSTOMER_360 = "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)"
MARKETING = "urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)"


async def verify_datahub_mcp() -> None:
    client = DataHubClient()
    discovery = await client.mcp_client.discover_tools()
    required = set(client.mcp_client.REQUIRED_READ_TOOLS)
    if not discovery.connected:
        raise RuntimeError(f"MCP connectivity failed: {discovery.error_message}")
    missing = required - set(discovery.tools)
    if missing:
        raise RuntimeError(f"Required MCP tools missing: {sorted(missing)}")
    logger.info("MCP connected; discovered tools: %s", ", ".join(sorted(discovery.tools)))

    mode = await client.get_integration_mode(False)
    if mode != IntegrationMode.LIVE_DATAHUB:
        raise RuntimeError(f"Expected LIVE_DATAHUB, got {mode.value}")

    dataset = await client.get_dataset(RAW, False)
    if not dataset or not dataset.provenance or dataset.provenance.source_mode != IntegrationMode.LIVE_DATAHUB:
        raise RuntimeError("raw_customers was not retrieved with LIVE_DATAHUB provenance")
    if not dataset.schema_verified or not {field.field_path for field in dataset.fields}.issuperset({"customer_id", "email"}):
        raise RuntimeError("raw_customers schema is missing required fields")
    if not dataset.owners or not dataset.tags:
        raise RuntimeError("raw_customers owners/tags were not retrieved")

    lineage = await client.get_downstream_lineage(RAW, max_depth=3, allow_fixture_fallback=False)
    if not lineage:
        raise RuntimeError("get_lineage returned zero downstream entities")
    lineage_urns = {node["entity"] for node in lineage}
    if CUSTOMER_360 not in lineage_urns or MARKETING not in lineage_urns:
        raise RuntimeError("Expected customer_360 and marketing_dashboard downstream lineage is absent")
    if any(node.get("source_mode") != IntegrationMode.LIVE_DATAHUB.value for node in lineage):
        raise RuntimeError("Lineage result contains non-live provenance")

    column_edges = await client.get_column_lineage(RAW, "email", False)
    if not any(edge.target_urn == CUSTOMER_360 for edge in column_edges):
        raise RuntimeError("email column lineage to customer_360 was not returned")
    exact = await client.verify_exact_lineage_path(RAW, CUSTOMER_360, "email", "email")
    if not exact:
        raise RuntimeError("get_lineage_paths_between did not return a matching email path")

    queries = await client.get_dataset_queries(RAW, "email", False)
    if not queries:
        raise RuntimeError("get_dataset_queries returned no canonical seeded email query")
    logger.info("Query usage records returned: %d canonical seeded record(s)", len(queries))
    logger.info("LIVE_DATAHUB demo verification passed")


def verify_authenticated_writeback(investigation_id: str) -> str:
    """Exercise the authenticated approval endpoint and real local DataHub mutations."""
    from fastapi.testclient import TestClient

    from app.config import settings

    if urlparse(settings.DATAHUB_GMS_URL).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Mutation verification is restricted to a local DataHub instance")

    auth_token = secrets.token_urlsafe(32)
    os.environ["SENTINEL_AUTH_TOKEN"] = auth_token
    os.environ["DATAHUB_MUTATION_ENABLED"] = "true"
    os.environ["TOOLS_IS_MUTATION_ENABLED"] = "true"
    os.environ["SAVE_DOCUMENT_TOOL_ENABLED"] = "true"
    settings.AUTH_MODE = "static"
    settings.SENTINEL_AUTH_TOKEN = auth_token

    from app.main import app

    with TestClient(app) as api:
        unauthenticated = api.post(f"/api/investigations/{investigation_id}/approve")
        if unauthenticated.status_code != 401:
            raise RuntimeError(
                f"Unauthenticated approval did not fail closed: HTTP {unauthenticated.status_code}"
            )

        headers = {"Authorization": f"Bearer {auth_token}"}
        approval = api.post(f"/api/investigations/{investigation_id}/approve", headers=headers)
        if approval.status_code != 200 or approval.json().get("status") != "APPROVED":
            raise RuntimeError(f"Authenticated approval failed: HTTP {approval.status_code} {approval.text}")

        writeback = api.post(f"/api/investigations/{investigation_id}/writeback", headers=headers)
        if writeback.status_code != 200:
            raise RuntimeError(f"Authenticated writeback failed: HTTP {writeback.status_code} {writeback.text}")
        payload = writeback.json()
        if payload.get("status") != "SUCCESS" or payload.get("success") is not True:
            raise RuntimeError(f"Writeback did not report verified success: {payload}")
        document_urn = payload.get("document_urn")
        if not isinstance(document_urn, str) or not document_urn.startswith("urn:li:document:"):
            raise RuntimeError("Writeback did not return a real DataHub document URN")

        events = api.get(f"/api/investigations/{investigation_id}/events")
        if events.status_code != 200:
            raise RuntimeError("Persisted investigation events could not be retrieved")
        event_rows = events.json()
        if not any(row.get("stage") == "APPROVAL" and row.get("status") == "APPROVED" for row in event_rows):
            raise RuntimeError("Persisted APPROVAL audit event is missing")
        if not any(row.get("stage") == "WRITEBACK" and row.get("status") == "SUCCESS" for row in event_rows):
            raise RuntimeError("Persisted successful WRITEBACK audit event is missing")

    return document_urn


async def verify_written_metadata(document_urn: str) -> None:
    client = DataHubClient()
    document = await client.mcp_client.get_entities([document_urn])
    if not document.success or not document.content:
        raise RuntimeError("Created investigation document could not be retrieved through MCP")
    documents = document.content.get("results") or []
    if not any(item.get("urn") == document_urn for item in documents if isinstance(item, dict)):
        raise RuntimeError("MCP document retrieval did not contain the returned document URN")

    dataset = await client.mcp_client.get_entities([RAW])
    entities = dataset.content.get("results", []) if dataset.success and dataset.content else []
    entity = entities[0] if entities and isinstance(entities[0], dict) else {}
    tag_block = entity.get("tags") if isinstance(entity.get("tags"), dict) else {}
    tag_urns = {
        tag.get("tag", {}).get("urn")
        for tag in tag_block.get("tags", [])
        if isinstance(tag, dict) and isinstance(tag.get("tag"), dict)
    }
    if "urn:li:tag:Sentinel_BLOCK" not in tag_urns:
        raise RuntimeError("Sentinel_BLOCK tag was not observable on raw_customers through MCP")
    logger.info("Authenticated approval, document writeback, tag writeback, and MCP retrieval passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-mutations",
        action="store_true",
        help="Enable controlled mutations against localhost and verify authenticated writeback",
    )
    parser.add_argument(
        "--investigation-id",
        help="Persisted investigation to approve and write back; required with --test-mutations",
    )
    args = parser.parse_args()
    try:
        asyncio.run(verify_datahub_mcp())
        if args.test_mutations:
            if not args.investigation_id:
                raise RuntimeError("--investigation-id is required with --test-mutations")
            written_document_urn = verify_authenticated_writeback(args.investigation_id)
            asyncio.run(verify_written_metadata(written_document_urn))
    except Exception as exc:
        logger.error("VERIFICATION FAILED: %s", exc)
        raise SystemExit(1) from exc
