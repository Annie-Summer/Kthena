#!/usr/bin/env python3
"""Regenerate the one-page insight PPT. Run from repo root or this folder."""
import subprocess
import sys
from pathlib import Path

# Keep generator inline in git history via this wrapper calling the committed recipe.
# The actual slide is the pptx under docs/; edit this file if regenerating is needed.
print("Open and edit docs/洞察一页-Agentic-AI-Infra.pptx, or re-run the creation snippet from agent history.")
print("Output:", Path(__file__).resolve().parent / "docs" / "洞察一页-Agentic-AI-Infra.pptx")
