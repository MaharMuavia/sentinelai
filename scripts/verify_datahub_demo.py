#!/usr/bin/env python3
"""
Sentinel AI — DataHub MCP Smoke Test & Verification Script
Queries seeded DataHub demo metadata back through the REAL DataHubMCPClient context provider.
Exits 0 if metadata is verified, or exits non-zero if GMS is offline or metadata is missing.
"""

import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from app.datahub.client import DataHubClient, IntegrationMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel.verify")


async def verify_datahub_mcp():
    logger.info("Initializing DataHub MCP Client verification...")
    client = DataHubClient()

    # 1. Connection Check
    if not await client.check_connection():
        logger.error("VERIFICATION FAILED: DataHub GMS / MCP Server is offline or unreachable.")
        sys.exit(1)

    logger.info("DataHub MCP Server is reachable!")

    # 2. Integration Mode Check
    mode = await client.get_integration_mode(allow_fixture_fallback=False)
    if mode != IntegrationMode.LIVE_DATAHUB:
        logger.error(f"VERIFICATION FAILED: Expected LIVE_DATAHUB mode, got {mode}")
        sys.exit(1)

    logger.info("Integration mode verified: LIVE_DATAHUB")

    # 3. Entity & Schema Verification via MCP
    target_urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    dataset = await client.get_dataset(target_urn, allow_fixture_fallback=False)
    if not dataset:
        logger.error(f"VERIFICATION FAILED: Could not retrieve dataset {target_urn} via DataHub MCP")
        sys.exit(1)

    logger.info(f"Retrieved dataset '{dataset.name}' via MCP tool: {dataset.provenance.source_tool if dataset.provenance else 'unknown'}")

    # 4. Downstream Lineage Verification via MCP
    lineage = await client.get_downstream_lineage(target_urn, max_depth=3, allow_fixture_fallback=False)
    logger.info(f"Retrieved {len(lineage)} downstream lineage nodes via MCP.")

    logger.info("DataHub MCP Integration Verification PASSED SUCCESSFULLY!")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(verify_datahub_mcp())
