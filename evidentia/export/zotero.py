"""Zotero integration — export citations directly to a Zotero library."""

from __future__ import annotations

from typing import Any

import httpx

from evidentia.core.logging import get_logger

logger = get_logger(__name__)

ZOTERO_API_URL = "https://api.zotero.org"

# ── CSL type -> Zotero itemType mapping ─────────────────────────────

_CSL_TO_ZOTERO_TYPE: dict[str, str] = {
    "article": "journalArticle",
    "article-journal": "journalArticle",
    "paper-conference": "conferencePaper",
    "book": "book",
    "chapter": "bookSection",
    "webpage": "webpage",
    "thesis": "thesis",
    "report": "report",
    "dataset": "document",
}


class ZoteroClient:
    """Client for the Zotero Web API v3.

    Supports both personal libraries (``user_id``) and group libraries
    (``group_id``).  If both are provided the group library takes
    precedence.
    """

    def __init__(
        self,
        api_key: str,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._user_id = user_id
        self._group_id = group_id

    # ── URL / header helpers ────────────────────────────────────────

    @property
    def _base_url(self) -> str:
        if self._group_id:
            return f"{ZOTERO_API_URL}/groups/{self._group_id}"
        return f"{ZOTERO_API_URL}/users/{self._user_id}"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Zotero-API-Key": self._api_key,
            "Zotero-API-Version": "3",
            "Content-Type": "application/json",
        }

    # ── Public methods ──────────────────────────────────────────────

    async def verify_key(self) -> bool:
        """Verify that the API key is valid and has appropriate access."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ZOTERO_API_URL}/keys/{self._api_key}",
                headers=self._headers,
            )
            if resp.status_code == 200:
                logger.info("zotero_key_valid")
                return True
            logger.warning("zotero_key_invalid", status=resp.status_code)
            return False

    async def create_items(
        self,
        items: list[dict[str, Any]],
        collection_id: str | None = None,
    ) -> dict[str, Any]:
        """Create items in the Zotero library.

        Zotero accepts up to **50 items per request**.  This method
        automatically batches larger lists.

        Args:
            items: CSL-JSON dicts to import.
            collection_id: Optional collection key to file items into.

        Returns:
            A summary dict with ``"success"``, ``"failed"``, and
            ``"unchanged"`` counts plus any error details.
        """
        zotero_items = [self.csl_to_zotero_item(item, collection_id) for item in items]

        total_success = 0
        total_failed = 0
        total_unchanged = 0
        errors: list[dict[str, Any]] = []

        # Zotero max batch size is 50
        batch_size = 50
        for start in range(0, len(zotero_items), batch_size):
            batch = zotero_items[start : start + batch_size]
            result = await self._post_items(batch)
            total_success += result.get("success_count", 0)
            total_failed += result.get("failed_count", 0)
            total_unchanged += result.get("unchanged_count", 0)
            if result.get("errors"):
                errors.extend(result["errors"])

        summary: dict[str, Any] = {
            "success": total_success,
            "failed": total_failed,
            "unchanged": total_unchanged,
            "total": len(zotero_items),
        }
        if errors:
            summary["errors"] = errors

        logger.info(
            "zotero_items_created",
            success=total_success,
            failed=total_failed,
            total=len(zotero_items),
        )
        return summary

    async def get_collections(self) -> list[dict[str, Any]]:
        """List all collections in the library."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self._base_url}/collections",
                headers=self._headers,
            )
            resp.raise_for_status()
            raw: list[dict[str, Any]] = resp.json()
            return [
                {
                    "key": col["key"],
                    "name": col["data"]["name"],
                    "parent": col["data"].get("parentCollection", None),
                }
                for col in raw
            ]

    # ── Format conversion ───────────────────────────────────────────

    @staticmethod
    def csl_to_zotero_item(
        csl_item: dict[str, Any],
        collection_id: str | None = None,
    ) -> dict[str, Any]:
        """Convert a CSL-JSON item dict to Zotero's write-API format.

        Zotero's expected shape::

            {
                "itemType": "journalArticle",
                "title": "...",
                "creators": [
                    {"creatorType": "author", "firstName": "...", "lastName": "..."}
                ],
                "date": "2024-01-15",
                "DOI": "...",
                "url": "...",
                "abstractNote": "...",
                "publicationTitle": "...",
            }
        """
        csl_type = csl_item.get("type", "article")
        item_type = _CSL_TO_ZOTERO_TYPE.get(csl_type, "journalArticle")

        # --- creators ---
        creators: list[dict[str, str]] = []
        for author in csl_item.get("author", []):
            creator: dict[str, str] = {"creatorType": "author"}
            family = author.get("family", "")
            given = author.get("given", "")
            if family:
                creator["lastName"] = family
            if given:
                creator["firstName"] = given
            # Fall back: if only "literal" key (some CSL sources)
            if not family and not given:
                literal = author.get("literal", "")
                creator["lastName"] = literal
                creator["firstName"] = ""
            creators.append(creator)

        # --- date ---
        date_str = ""
        issued = csl_item.get("issued")
        if issued and isinstance(issued, dict):
            date_parts = issued.get("date-parts", [[]])
            if date_parts and date_parts[0]:
                parts = date_parts[0]
                date_str = "-".join(str(p).zfill(2) if i > 0 else str(p) for i, p in enumerate(parts))

        zotero_item: dict[str, Any] = {
            "itemType": item_type,
            "title": csl_item.get("title", ""),
            "creators": creators,
        }

        if date_str:
            zotero_item["date"] = date_str
        if csl_item.get("DOI"):
            zotero_item["DOI"] = csl_item["DOI"]
        if csl_item.get("URL"):
            zotero_item["url"] = csl_item["URL"]
        if csl_item.get("abstract"):
            zotero_item["abstractNote"] = csl_item["abstract"]
        if csl_item.get("container-title"):
            zotero_item["publicationTitle"] = csl_item["container-title"]
        if csl_item.get("volume"):
            zotero_item["volume"] = csl_item["volume"]
        if csl_item.get("page"):
            zotero_item["pages"] = csl_item["page"]

        if collection_id:
            zotero_item["collections"] = [collection_id]

        return zotero_item

    # ── Private helpers ─────────────────────────────────────────────

    async def _post_items(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """POST a batch of Zotero items (max 50)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/items",
                headers=self._headers,
                json=items,
            )

            if resp.status_code not in (200, 201):
                logger.error(
                    "zotero_post_failed",
                    status=resp.status_code,
                    body=resp.text[:500],
                )
                return {
                    "success_count": 0,
                    "failed_count": len(items),
                    "unchanged_count": 0,
                    "errors": [{"status": resp.status_code, "message": resp.text[:500]}],
                }

            body = resp.json()
            success_map: dict[str, Any] = body.get("success", body.get("successful", {}))
            failed_map: dict[str, Any] = body.get("failed", {})
            unchanged_map: dict[str, Any] = body.get("unchanged", {})

            errors: list[dict[str, Any]] = []
            for key, detail in failed_map.items():
                errors.append({"index": key, "detail": detail})

            return {
                "success_count": len(success_map),
                "failed_count": len(failed_map),
                "unchanged_count": len(unchanged_map),
                "errors": errors,
            }
