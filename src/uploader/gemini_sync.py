"""Upload / replace Markdown files in a Gemini File Search store via API."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from google import genai

logger = logging.getLogger("optibot.uploader")

# Rough estimate when Gemini does not return chunk counts on upload.
AVG_CHARS_PER_CHUNK = 3200


class GeminiSync:
    def __init__(self, *, api_key: str, file_search_store: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.file_search_store = file_search_store

    def remove_document(self, document_name: str) -> None:
        """Delete a document from the file search store."""
        if not document_name.startswith("fileSearchStores/"):
            logger.warning("Skipping delete for non-Gemini document id: %s", document_name)
            return
        try:
            self.client.file_search_stores.documents.delete(name=document_name)
            logger.info("Deleted Gemini document %s", document_name)
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            logger.warning("Could not delete document %s: %s", document_name, exc)

    def upload_markdown(
        self,
        path: Path,
        *,
        poll_interval_s: float = 2.0,
        poll_timeout_s: float = 300.0,
    ) -> tuple[str, int]:
        """Upload a .md file into the file search store.

        Returns ``(document_name, estimated_chunk_count)``.
        """
        size = path.stat().st_size
        estimated_chunks = max(1, (size + AVG_CHARS_PER_CHUNK - 1) // AVG_CHARS_PER_CHUNK)

        operation = self.client.file_search_stores.upload_to_file_search_store(
            file=str(path),
            file_search_store_name=self.file_search_store,
            config={"display_name": path.name},
        )
        logger.info(
            "Uploading %s to %s (%d bytes, ≈%d chunks)…",
            path.name,
            self.file_search_store,
            size,
            estimated_chunks,
        )

        document_name = self._wait_for_upload(
            operation,
            poll_interval_s=poll_interval_s,
            poll_timeout_s=poll_timeout_s,
        )
        time.sleep(0.25)
        return document_name, int(estimated_chunks)

    def _wait_for_upload(self, operation, *, poll_interval_s: float, poll_timeout_s: float) -> str:
        deadline = time.time() + poll_timeout_s
        while not operation.done:
            if time.time() >= deadline:
                raise TimeoutError("Timed out waiting for Gemini file search upload")
            time.sleep(poll_interval_s)
            operation = self.client.operations.get(operation)

        if getattr(operation, "error", None):
            raise RuntimeError(f"Gemini upload failed: {operation.error}")

        document_name = self._document_name_from_operation(operation)
        if not document_name:
            raise RuntimeError(f"Upload finished but no document_name in operation: {operation!r}")

        logger.info("Uploaded -> %s", document_name)
        return document_name

    @staticmethod
    def _document_name_from_operation(operation) -> str | None:
        response = getattr(operation, "response", None)
        if response is None:
            return None
        if isinstance(response, dict):
            return response.get("document_name") or response.get("name")
        return getattr(response, "document_name", None) or getattr(response, "name", None)
