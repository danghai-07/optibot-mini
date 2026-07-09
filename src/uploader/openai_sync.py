"""Upload / replace Markdown files in an OpenAI Vector Store via API."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger("optibot.uploader")

# Rough estimate when OpenAI does not return chunk counts on the file object.
AVG_CHARS_PER_CHUNK = 3200


class OpenAISync:
    def __init__(self, *, api_key: str, vector_store_id: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.vector_store_id = vector_store_id

    def remove_file(self, openai_file_id: str) -> None:
        """Detach from vector store (if present) then delete the file object."""
        try:
            self.client.vector_stores.files.delete(
                vector_store_id=self.vector_store_id,
                file_id=openai_file_id,
            )
            logger.info("Detached %s from vector store", openai_file_id)
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            logger.warning("Could not detach %s: %s", openai_file_id, exc)

        try:
            self.client.files.delete(openai_file_id)
            logger.info("Deleted OpenAI file %s", openai_file_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not delete file %s: %s", openai_file_id, exc)

    def upload_markdown(self, path: Path, *, poll_timeout_s: float = 180.0) -> tuple[str, int]:
        """Upload a .md file and attach it to the vector store.

        Returns ``(file_id, estimated_chunk_count)``.
        """
        size = path.stat().st_size
        estimated_chunks = max(1, (size + AVG_CHARS_PER_CHUNK - 1) // AVG_CHARS_PER_CHUNK)

        with path.open("rb") as fh:
            created = self.client.files.create(file=fh, purpose="assistants")
        file_id = created.id
        logger.info("Uploaded %s -> %s (%d bytes, ≈%d chunks)", path.name, file_id, size, estimated_chunks)

        self.client.vector_stores.files.create(
            vector_store_id=self.vector_store_id,
            file_id=file_id,
        )

        self._wait_until_ready(file_id, timeout_s=poll_timeout_s)
        # Gentle pacing for bulk first-time syncs
        time.sleep(0.25)
        return file_id, int(estimated_chunks)

    def _wait_until_ready(self, file_id: str, *, timeout_s: float) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            vs_file = self.client.vector_stores.files.retrieve(
                vector_store_id=self.vector_store_id,
                file_id=file_id,
            )
            status = getattr(vs_file, "status", None)
            if status == "completed":
                return
            if status == "failed":
                last_error = getattr(vs_file, "last_error", None)
                raise RuntimeError(f"Vector store ingest failed for {file_id}: {last_error}")
            time.sleep(1.5)
        raise TimeoutError(f"Timed out waiting for vector store file {file_id}")
