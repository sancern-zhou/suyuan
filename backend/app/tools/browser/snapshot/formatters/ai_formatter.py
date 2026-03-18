"""AI Formatter - LLM Optimized Snapshot Format

Generates LLM-friendly page snapshots with semantic role-based references.
Optimized for LLM understanding and interaction.

Based on moltbot-main pw-role-snapshot.ts implementation.
"""
import structlog
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from playwright.sync_api import Page

from ...refs.role_ref import RoleRef, INTERACTIVE_ROLES

logger = structlog.get_logger()


class RoleNameTracker:
    """Tracker for role-name combinations to identify duplicates

    Based on moltbot createRoleNameTracker implementation.

    Tracks:
    - counts: Map of (role, name) -> occurrence count
    - refs_by_key: Map of (role, name) -> list of ref IDs

    Used to:
    1. Assign nth index to duplicate elements
    2. Identify which elements are duplicates
    3. Remove nth from non-duplicate elements (optimization)
    """

    def __init__(self):
        self.counts: Dict[Tuple[str, str], int] = {}
        self.refs_by_key: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    def get_key(self, role: str, name: Optional[str]) -> Tuple[str, str]:
        """Get unique key for role-name combination

        Args:
            role: ARIA role
            name: Accessible name (optional)

        Returns:
            Tuple key for tracking
        """
        return (role, name or "")

    def get_next_index(self, role: str, name: Optional[str]) -> int:
        """Get next index for this role-name combination

        Args:
            role: ARIA role
            name: Accessible name (optional)

        Returns:
            Current index (0-based, increments after each call)
        """
        key = self.get_key(role, name)
        current = self.counts.get(key, 0)
        self.counts[key] = current + 1
        return current

    def track_ref(self, role: str, name: Optional[str], ref: str) -> None:
        """Track a ref ID for this role-name combination

        Args:
            role: ARIA role
            name: Accessible name (optional)
            ref: Reference ID (e.g., "e1")
        """
        key = self.get_key(role, name)
        self.refs_by_key[key].append(ref)

    def get_duplicate_keys(self) -> Set[Tuple[str, str]]:
        """Get all role-name keys that have duplicates

        Returns:
            Set of keys that have more than one ref
        """
        duplicates = set()
        for key, refs in self.refs_by_key.items():
            if len(refs) > 1:
                duplicates.add(key)
        return duplicates


class AIFormatter:
    """AI Format Snapshot Generator

    Creates LLM-optimized snapshots with:
    - Semantic role-based element references (e1, e2, etc.)
    - Accessible names for better element identification
    - Interactive element filtering
    - Compact text representation

    Example output:
        [e1] button: "Login"
        [e2] textbox: "Username"
        [e3] textbox: "Password"
        [e4] link: "Forgot password?"
    """

    # CSS selector for interactive elements
    # Extended to capture custom components and non-standard interactive elements
    # IMPORTANT: Exclude hidden elements to avoid including non-interactive inputs
    INTERACTIVE_SELECTOR = """
    button, [role="button"],
    input:not([type="hidden"]):not([hidden]),
    textarea:not([hidden]):not([style*="display: none"]):not([style*="display:none"]),
    select:not([hidden]), [role="combobox"],
    a:not([hidden]), [role="link"],
    [role="checkbox"]:not([hidden]), [role="radio"]:not([hidden]),
    [role="listbox"]:not([hidden]), [role="slider"]:not([hidden]),
    [role="searchbox"]:not([hidden]), [role="spinbutton"]:not([hidden]),
    [role="tab"]:not([hidden]), [role="menuitem"]:not([hidden]),
    /* Extended: div/span with click handlers (only if visible) */
    div[onclick]:not([hidden]), div[class*="btn"]:not([hidden]), div[class*="button"]:not([hidden]),
    span[onclick]:not([hidden]), span[class*="btn"]:not([hidden]), span[class*="button"]:not([hidden]),
    /* Extended: common card-like interactive elements */
    [class*="card"][onclick]:not([hidden]), [class*="item"][onclick]:not([hidden]),
    /* Extended: Element UI components */
    .el-button:not([hidden]), .el-card:not([hidden]), .el-menu-item:not([hidden]),
    /* Extended: common UI framework button patterns */
    [class*="-button"]:not([hidden]), [class*="-btn"]:not([hidden]), [class*="_button"]:not([hidden]), [class*="_btn"]:not([hidden]),
    [class*="clickable"]:not([hidden]), [class*="interactive"]:not([hidden]),
    /* Extended: data-* attributes for interactivity */
    [data-action]:not([hidden]), [data-click]:not([hidden]), [data-toggle]:not([hidden])
    """

    # Structural roles that can be removed in compact mode
    STRUCTURAL_ROLES = {"generic", "group", "list", "root", "presentation"}

    def format(
        self,
        page: Page,
        max_refs: int = 100,
        interactive_only: bool = False,
        depth: int = 10,
        compact: bool = False
    ) -> Dict:
        """Generate AI format snapshot

        Args:
            page: Playwright Page instance
            max_refs: Maximum number of refs to generate
            interactive_only: Only include interactive elements
            depth: DOM traversal depth (not used in current implementation)
            compact: Remove unnamed structural elements (generic, group, etc.)

        Returns:
            {
                "ok": True,
                "format": "ai",
                "snapshot": str,  # Formatted snapshot text
                "refs": {...},     # Reference context for resolver
                "stats": {...}     # Statistics
            }
        """
        refs = {}
        lines = []
        ref_count = 0

        # Use RoleNameTracker for intelligent nth handling
        tracker = RoleNameTracker()

        try:
            # Get interactive elements
            elements = page.query_selector_all(self.INTERACTIVE_SELECTOR)

            for element in elements:
                if ref_count >= max_refs:
                    break

                try:
                    # Create role reference from element
                    ref_id = f"e{ref_count + 1}"
                    role_ref = RoleRef.from_element(ref_id, element)

                    # Filter non-interactive elements if requested
                    if interactive_only and not RoleRef.is_interactive(role_ref.role):
                        continue

                    # Filter structural elements in compact mode
                    # Remove unnamed structural elements (generic, group, etc.)
                    if compact and self._is_structural_and_unnamed(role_ref):
                        continue

                    # Calculate nth index using tracker
                    nth = tracker.get_next_index(role_ref.role, role_ref.name)
                    tracker.track_ref(role_ref.role, role_ref.name, ref_id)

                    # Store nth in role_ref (will be cleaned up later if not a duplicate)
                    if nth > 0:
                        role_ref.nth = nth

                    # Store reference context (enhanced with selector and html_attrs)
                    refs[ref_id] = {
                        "role": role_ref.role,
                        "name": role_ref.name,
                    }

                    # Add optional fields if available
                    if role_ref.nth is not None and role_ref.nth > 0:
                        refs[ref_id]["nth"] = role_ref.nth

                    if role_ref.selector:
                        refs[ref_id]["selector"] = role_ref.selector

                    if role_ref.html_attrs:
                        refs[ref_id]["html_attrs"] = role_ref.html_attrs

                    # Format line
                    line = str(role_ref)
                    lines.append(line)

                    ref_count += 1

                except Exception as e:
                    # Skip elements that can't be processed
                    logger.debug("[AI_FORMATTER] Skipping element", error=str(e))
                    continue

            # Remove nth from non-duplicate elements (optimization)
            self._remove_nth_from_non_duplicates(refs, tracker)

            # Regenerate snapshot lines after nth cleanup
            lines = []
            for ref_id, ref_data in refs.items():
                role = ref_data["role"]
                name = ref_data.get("name")
                nth = ref_data.get("nth")

                # Format line with updated nth values
                base = f"[{ref_id}] {role}"
                if name:
                    base += f": \"{name}\""
                if nth is not None and nth > 0:
                    base += f" [nth={nth}]"
                lines.append(base)

            snapshot_text = "\n".join(lines)

            # Calculate statistics
            interactive_count = sum(
                1 for r in refs.values()
                if r["role"] in INTERACTIVE_ROLES
            )

            stats = {
                "total_refs": ref_count,
                "interactive_refs": interactive_count,
                "lines": len(lines),
                "chars": len(snapshot_text)
            }

            logger.info(
                "[AI_FORMATTER] Snapshot generated",
                format="ai",
                total_refs=ref_count,
                interactive_refs=interactive_count,
                chars=stats["chars"]
            )

            return {
                "ok": True,
                "format": "ai",
                "snapshot": snapshot_text,
                "refs": refs,
                "stats": stats
            }

        except Exception as e:
            logger.error("[AI_FORMATTER] Failed to generate snapshot", error=str(e))
            return {
                "ok": False,
                "format": "ai",
                "snapshot": "",
                "refs": {},
                "stats": {"error": str(e)}
            }

    def _remove_nth_from_non_duplicates(
        self,
        refs: Dict[str, dict],
        tracker: RoleNameTracker
    ) -> None:
        """Remove nth index from non-duplicate elements

        Based on moltbot removeNthFromNonDuplicates implementation.

        Optimization: Only elements that are truly duplicates need nth index.
        For example:
            [e1] button: "Login"     -> unique, no nth needed
            [e2] button: "Register"  -> unique, no nth needed
            [e3] button: "Submit"    -> duplicate, needs nth=1

        Args:
            refs: Dictionary of refs with potential nth values
            tracker: RoleNameTracker with duplicate information
        """
        duplicates = tracker.get_duplicate_keys()

        for ref_id, ref_data in refs.items():
            key = tracker.get_key(ref_data["role"], ref_data.get("name"))
            if key not in duplicates:
                # Not a duplicate, remove nth if present
                ref_data.pop("nth", None)

    def _is_structural_and_unnamed(self, role_ref: RoleRef) -> bool:
        """Check if element is a structural element without a name

        Based on moltbot compact mode logic:
        - Remove unnamed structural elements (generic, group, list, etc.)
        - Keep elements with names (they provide context)
        - Keep interactive elements

        Args:
            role_ref: RoleRef to check

        Returns:
            True if element should be filtered in compact mode
        """
        # Keep elements with names (they provide useful context)
        if role_ref.name:
            return False

        # Keep interactive elements
        if RoleRef.is_interactive(role_ref.role):
            return False

        # Filter unnamed structural elements
        return role_ref.role in self.STRUCTURAL_ROLES

    def get_page_text(self, page: Page, max_length: int = 10000) -> str:
        """Get page text content (fallback for plain text)

        Args:
            page: Playwright Page instance
            max_length: Maximum text length

        Returns:
            Page text content
        """
        try:
            text = page.evaluate("() => document.body.innerText")
            if text and len(text) > max_length:
                text = text[:max_length]
            return text or ""
        except Exception as e:
            logger.warning("[AI_FORMATTER] Failed to get page text", error=str(e))
            return ""
