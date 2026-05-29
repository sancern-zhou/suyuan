from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class TemplateManifest(BaseModel):
    template: str
    slots: Dict[str, str] = Field(default_factory=dict)

    def to_physical_replacements(self, semantic_values: Dict[str, Any]) -> Dict[str, Any]:
        replacements: Dict[str, Any] = {}
        for semantic_slot, value in semantic_values.items():
            physical_slot = self.slots.get(semantic_slot)
            if physical_slot:
                replacements[physical_slot] = value
        return replacements

    def unknown_semantic_slots(self, semantic_values: Dict[str, Any]) -> List[str]:
        return [slot for slot in semantic_values if slot not in self.slots]
