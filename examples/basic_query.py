"""Example: Running a basic research query through Evidentia.

This example demonstrates how to use the Evidentia SDK to:
1. Configure the tool registry
2. Build the orchestration pipeline
3. Execute a research query
4. Inspect the structured results
"""

import asyncio

from evidentia.schemas.api import QueryRequest
from evidentia.tools.arxiv import ArxivTool
from evidentia.tools.base import ToolRegistry
from evidentia.tools.semantic_scholar import SemanticScholarTool


async def main():
    # 1. Register tools
    registry = ToolRegistry()
    registry.register(ArxivTool())
    registry.register(SemanticScholarTool())

    print(f"Registered {len(registry.tool_names)} tools: {registry.tool_names}")

    # 2. Create a query
    _request = QueryRequest(
        query="What are the latest advances in protein structure prediction?",
        max_steps=10,
    )

    # 3. The full pipeline would run:
    #    Planner -> ToolRouter -> Validator -> DecisionEngine
    #
    #    For now, let's demonstrate individual tool execution:

    print("\n--- ArXiv Search ---")
    arxiv = ArxivTool()
    result = await arxiv.execute({"query": "protein structure prediction", "max_results": 3})
    for paper in result.get("data", []):
        print(f"  [{paper['arxiv_id']}] {paper['title']}")
        print(f"    Authors: {', '.join(paper['authors'][:3])}")
        print()

    print("\n--- Semantic Scholar Search ---")
    s2 = SemanticScholarTool()
    result = await s2.execute({"query": "protein folding AlphaFold", "max_results": 3})
    for paper in result.get("data", []):
        print(f"  {paper['title']} (citations: {paper.get('citation_count', 'N/A')})")
        print()


if __name__ == "__main__":
    asyncio.run(main())
