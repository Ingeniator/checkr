"""
---
title: Base GABRIEL Validator
type: base
description: Abstract base class for GABRIEL-based validators using OpenAI's GABRIEL library for structured text evaluation.
tags: [abstract, gabriel, quality, semantic]
---
"""

import asyncio
import os
import shutil
import tempfile
from abc import ABC, abstractmethod

import pandas as pd

from core.config import settings
from utils.yaml import load_and_expand_yaml
from validators.base_validator import BaseValidator, MessagesItem, ValidationDetail

_gabriel_import_error: str | None = None
try:
    import gabriel
except Exception as _e:
    gabriel = None
    _gabriel_import_error = str(_e)


class BaseGabrielValidator(BaseValidator, ABC):
    """Base class for all GABRIEL-powered validators.

    Handles data conversion, LLM config, environment setup,
    temp directory management, and the abstract interface.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        config_path = settings.llm_config_path
        full_config = load_and_expand_yaml(config_path)
        self.config = full_config.get("gabriel", full_config.get("geval", {}))

    @staticmethod
    def messages_to_dataframe(data: list[MessagesItem]) -> pd.DataFrame:
        """Convert list[MessagesItem] to a pandas DataFrame.

        Each dialog becomes one row with columns:
        - text: concatenated assistant responses
        - user_text: concatenated user messages
        - full_dialog: all messages with role prefixes
        - item_index: original index in the dataset
        """
        rows = []
        for idx, item in enumerate(data):
            assistant_parts = []
            user_parts = []
            dialog_parts = []

            for msg in item.messages:
                dialog_parts.append(f"{msg.role}: {msg.content}")
                if msg.role == "assistant":
                    assistant_parts.append(msg.content)
                elif msg.role == "user":
                    user_parts.append(msg.content)

            rows.append({
                "item_index": idx,
                "text": "\n\n".join(assistant_parts),
                "user_text": "\n\n".join(user_parts),
                "full_dialog": "\n".join(dialog_parts),
            })

        return pd.DataFrame(rows)

    @abstractmethod
    async def _run_gabriel(
        self, df: pd.DataFrame, text_column: str, save_dir: str
    ) -> pd.DataFrame:
        """Run the specific gabriel operation. Implemented by subclasses."""

    @abstractmethod
    def _interpret_results(
        self,
        result_df: pd.DataFrame,
        input_df: pd.DataFrame,
        data: list[MessagesItem],
    ) -> list[ValidationDetail]:
        """Interpret gabriel results into validation errors. Implemented by subclasses."""

    async def _validate(self, data: list[MessagesItem]) -> list[ValidationDetail]:
        if gabriel is None:
            detail = _gabriel_import_error or "openai-gabriel is not installed"
            return [
                ValidationDetail(
                    error=f"GABRIEL library failed to load: {detail}. Install with: pip install openai-gabriel",
                    code="missing_dependency",
                )
            ]

        if not data:
            return []

        input_df = self.messages_to_dataframe(data)

        # Set up environment for gabriel
        original_api_key = os.environ.get("OPENAI_API_KEY")
        original_base_url = os.environ.get("OPENAI_BASE_URL")
        save_dir = tempfile.mkdtemp(prefix="checkr_gabriel_")

        try:
            api_key = self.config.get("api_key", "")
            api_base = self.config.get("api_base", "")

            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
            if api_base:
                os.environ["OPENAI_BASE_URL"] = api_base

            self.report_stage("running gabriel")
            result_df = await self._run_gabriel(input_df, "text", save_dir)

            # Re-join by positional index if gabriel didn't preserve item_index
            if "item_index" not in result_df.columns:
                result_df["item_index"] = input_df["item_index"].values[
                    : len(result_df)
                ]

            self.report_stage("interpreting results")
            return self._interpret_results(result_df, input_df, data)

        except Exception as e:
            return [
                ValidationDetail(
                    error=f"GABRIEL evaluation failed: {e}",
                    code="gabriel_error",
                )
            ]
        finally:
            # Restore original environment
            if original_api_key is not None:
                os.environ["OPENAI_API_KEY"] = original_api_key
            elif "OPENAI_API_KEY" in os.environ and api_key:
                del os.environ["OPENAI_API_KEY"]

            if original_base_url is not None:
                os.environ["OPENAI_BASE_URL"] = original_base_url
            elif "OPENAI_BASE_URL" in os.environ and api_base:
                del os.environ["OPENAI_BASE_URL"]

            # Clean up temp directory
            shutil.rmtree(save_dir, ignore_errors=True)
