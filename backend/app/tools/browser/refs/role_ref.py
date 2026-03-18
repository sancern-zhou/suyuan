"""Role-based Reference Implementation

Provides semantic role-based element references following ARIA roles.
Compatible with Playwright's get_by_role() API.

INTERACTIVE_ROLES: Based on WAI-ARIA 1.2 specification (44 roles)
- Covers all interactive widget roles
- Includes document structure roles that can be interactive
- Compatible with moltbot-main role definitions
"""
from dataclasses import dataclass
from typing import Optional, List
from playwright.sync_api import Page, Locator

from .base import BaseRef


# Interactive ARIA roles that should be included in snapshots
# Based on WAI-ARIA 1.2 specification and moltbot-main implementation
INTERACTIVE_ROLES = [
    # Core interactive elements
    "button",
    "link",
    "textbox",
    "checkbox",
    "radio",

    # Input variants
    "searchbox",
    "spinbutton",
    "combobox",
    "listbox",
    "slider",

    # Navigation and selection
    "tab",
    "tablist",
    "tabpanel",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "menu",
    "menubar",
    "option",

    # Tree structures
    "tree",
    "treeitem",
    "treegrid",

    # Grid structures
    "grid",
    "gridcell",
    "row",
    "columnheader",
    "rowheader",

    # Composite widgets
    "radiogroup",
    "switch",

    # Dialog and alert types
    "dialog",
    "alertdialog",
    "alert",
    "tooltip",

    # Progress and status
    "progressbar",
    "scrollbar",
    "separator",

    # Application structure (can be interactive in certain contexts)
    "application",
    "log",
    "marquee",
    "status",
    "timer",

    # Document structure
    "article",
    "document",
    "region"
]

# HTML tag to role mapping
TAG_ROLE_MAP = {
    "button": "button",
    "a": "link",
    "input": "textbox",  # Will be refined based on type
    "textarea": "textbox",
    "select": "combobox",
    "ul": "list",
    "ol": "list",
    "nav": "navigation",
    "main": "main",
    "header": "banner",
    "footer": "contentinfo",
    "article": "article",
    "aside": "complementary",
    "section": "region"
}


@dataclass
class RoleRef(BaseRef):
    """Role-based element reference

    Uses semantic role for element selection, following ARIA roles.
    Compatible with Playwright's get_by_role() API.

    Supports 44 interactive roles (v3.0):
    - Core: button, link, textbox, checkbox, radio
    - Inputs: searchbox, spinbutton, combobox, listbox, slider
    - Navigation: tab, tablist, tabpanel, menu, menubar, menuitem*
    - Trees: tree, treeitem, treegrid
    - Grids: grid, gridcell, row, columnheader, rowheader
    - Widgets: radiogroup, switch, progressbar, scrollbar, separator
    - Dialogs: dialog, alertdialog, alert, tooltip
    - Structure: application, article, document, region, log, status, timer

    Attributes:
        element_id: Unique identifier (e.g., "e1", "e2")
        role: ARIA role (button, textbox, link, combobox, etc.)
        name: Accessible name (for disambiguation)
        nth: Index for multiple matching elements (0-based)
        selector: Direct CSS selector (fallback for complex elements)
        html_attrs: Raw HTML attributes for reference

    Example:
        # Create role reference
        ref = RoleRef(element_id="e1", role="button", name="Login", nth=0)
        locator = ref.to_locator(page)
        locator.click()

        # String representation
        str(ref)  # "[e1] button: \"Login\""
    """
    role: str
    name: Optional[str] = None
    nth: Optional[int] = None
    selector: Optional[str] = None
    html_attrs: Optional[dict] = None

    def to_locator(self, page: Page) -> Locator:
        """Convert to Playwright Locator using get_by_role()

        Args:
            page: Playwright Page instance

        Returns:
            Playwright Locator object
        """
        kwargs = {}
        if self.name:
            kwargs['name'] = self.name
            kwargs['exact'] = True

        locator = page.get_by_role(self.role, **kwargs)

        # Apply nth index if specified (for handling duplicate elements)
        if self.nth is not None and self.nth > 0:
            locator = locator.nth(self.nth)

        return locator

    def __str__(self) -> str:
        """String representation for LLM consumption

        Returns:
            Format: [e1] button: "Login" or [e1] textbox or [e1] textbox: "Password" [nth=1]
        """
        base = f"[{self.element_id}] {self.role}"
        if self.name:
            base += f": \"{self.name}\""
        if self.nth is not None and self.nth > 0:
            base += f" [nth={self.nth}]"
        return base

    @classmethod
    def from_element(cls, element_id: str, element) -> 'RoleRef':
        """Create RoleRef from Playwright ElementHandle

        Args:
            element_id: Reference ID (e.g., "e1")
            element: Playwright ElementHandle

        Returns:
            RoleRef instance
        """
        # Get role from element
        role = cls._get_role(element)

        # Get name from element
        name = cls._get_name(element)

        # Get HTML attributes
        html_attrs = cls._get_html_attrs(element)

        # Generate a fallback selector based on attributes
        selector = cls._generate_selector(element, html_attrs)

        return cls(
            element_id=element_id,
            role=role,
            name=name,
            html_attrs=html_attrs,
            selector=selector
        )

    @staticmethod
    def _generate_selector(element, html_attrs: dict) -> str:
        """Generate a CSS selector based on element attributes

        Priority:
        1. id attribute
        2. name attribute
        3. placeholder attribute (for inputs)
        4. aria-label attribute
        5. tag name + class

        Args:
            element: Playwright ElementHandle
            html_attrs: Extracted HTML attributes

        Returns:
            CSS selector string
        """
        # Try ID first (most reliable)
        if 'id' in html_attrs and html_attrs['id']:
            return f"#{html_attrs['id']}"

        # Try name attribute
        if 'name' in html_attrs and html_attrs['name']:
            tag = element.evaluate("el => el.tagName.toLowerCase()")
            return f"{tag}[name='{html_attrs['name']}']"

        # Try placeholder (for text inputs)
        if 'placeholder' in html_attrs and html_attrs['placeholder']:
            tag = element.evaluate("el => el.tagName.toLowerCase()")
            return f"{tag}[placeholder='{html_attrs['placeholder']}']"

        # Try aria-label
        if 'aria-label' in html_attrs and html_attrs['aria-label']:
            return f"[aria-label='{html_attrs['aria-label']}']"

        # Fallback: tag + class (first class)
        if 'class' in html_attrs and html_attrs['class']:
            tag = element.evaluate("el => el.tagName.toLowerCase()")
            classes = html_attrs['class'].split()
            if classes:
                return f"{tag}.{classes[0]}"

        # Last resort: tag only
        tag = element.evaluate("el => el.tagName.toLowerCase()")
        return tag

    @staticmethod
    def _is_visible(element) -> bool:
        """Check if element is visible and interactive

        Based on moltbot's approach: only elements that can "respond" to user interaction.
        Filters out hidden, display:none, visibility:hidden, offsetParent=null elements.

        Args:
            element: Playwright ElementHandle

        Returns:
            True if element is visible and can receive user interaction
        """
        try:
            return element.evaluate("""
                el => {
                    // Check computed style
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') {
                        return false;
                    }

                    // Check if element has a size
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) {
                        return false;
                    }

                    // Check if element is in the DOM tree and has an offset parent
                    // (elements with display:none have offsetParent === null)
                    if (el.offsetParent === null) {
                        return false;
                    }

                    // Check for common hidden attributes
                    if (el.getAttribute('hidden') !== null) {
                        return false;
                    }

                    // Check for type="hidden" (form elements that shouldn't be interactive)
                    if (el.type === 'hidden') {
                        return false;
                    }

                    return true;
                }
            """)
        except Exception:
            # If visibility check fails, assume visible (don't filter out)
            return True

    @staticmethod
    def _get_role(element) -> str:
        """Extract role from element

        Priority:
        1. Explicit ARIA role attribute
        2. Inferred from tag name
        3. Inferred from class name patterns (for custom components)
        4. Inferred from click handlers
        5. Default to "generic"

        Args:
            element: Playwright ElementHandle

        Returns:
            Role string
        """
        # Check visibility first - filter out hidden elements early
        if not RoleRef._is_visible(element):
            return "generic"

        # Check for non-interactive tags (style, script, etc.)
        tag = element.evaluate("el => el.tagName.toLowerCase()")
        if tag in ["style", "script", "noscript", "meta", "link", "title"]:
            return "generic"

        # Try ARIA role first
        role = element.evaluate("el => el.getAttribute('role')")
        if role:
            return role.lower()

        # Infer from tag name
        if tag in TAG_ROLE_MAP:
            inferred_role = TAG_ROLE_MAP[tag]

            # Special handling for input elements
            if tag == "input":
                input_type = element.evaluate("el => el.type || 'text'")
                inferred_role = RoleRef._get_input_role(input_type)

            return inferred_role

        # Extended: Infer from class name patterns for div/span elements
        if tag in ["div", "span"]:
            class_name = element.evaluate("el => el.className || ''")
            onclick = element.evaluate("el => el.getAttribute('onclick')")

            # Check for button-like class names
            button_patterns = ["btn", "button", "card", "item", "clickable", "interactive"]
            if any(pattern in class_name.lower() for pattern in button_patterns):
                return "button"

            # Check for Element UI components
            if "el-button" in class_name or "el-card" in class_name or "el-menu-item" in class_name:
                return "button"

            # Check for click handlers
            if onclick or "click" in class_name.lower():
                return "button"

        # Check for data attributes indicating interactivity
        data_action = element.evaluate("el => el.getAttribute('data-action')")
        data_click = element.evaluate("el => el.getAttribute('data-click')")
        data_toggle = element.evaluate("el => el.getAttribute('data-toggle')")

        if data_action or data_click or data_toggle:
            return "button"

        return "generic"

    @staticmethod
    def _get_input_role(input_type: str) -> str:
        """Get role for input element based on type

        Args:
            input_type: Input type attribute

        Returns:
            ARIA role string
        """
        type_roles = {
            "text": "textbox",
            "password": "textbox",
            "email": "textbox",
            "tel": "textbox",
            "url": "textbox",
            "search": "searchbox",
            "number": "spinbutton",
            "checkbox": "checkbox",
            "radio": "radio",
            "submit": "button",
            "button": "button",
            "reset": "button",
            "image": "button",
            "file": "textbox",
            "date": "textbox",
            "time": "textbox",
            "datetime-local": "textbox",
            "range": "slider"
        }
        return type_roles.get(input_type.lower(), "textbox")

    @staticmethod
    def _get_html_attrs(element) -> dict:
        """Extract useful HTML attributes from element

        Args:
            element: Playwright ElementHandle

        Returns:
            Dictionary of HTML attributes
        """
        useful_attrs = [
            'id', 'name', 'class', 'type', 'placeholder',
            'value', 'href', 'src', 'alt', 'title',
            'data-action', 'data-click', 'data-toggle',
            'aria-label', 'role', 'disabled',
            'mu',  # ⭐ 百度搜索结果：包含真实URL
            'data-tools',  # ⭐ 百度搜索结果：包含工具信息
            'srcid',  # ⭐ 百度搜索结果：结果ID
            'tpl'  # ⭐ 百度搜索结果：模板类型
        ]

        attrs = {}
        for attr in useful_attrs:
            value = element.evaluate(f"el => el.getAttribute('{attr}')")
            if value is not None:
                attrs[attr] = value

        return attrs

    @staticmethod
    def _get_name(element) -> str:
        """Extract accessible name from element

        Priority:
        1. aria-label attribute
        2. Text content (limited to 50 chars)
        3. placeholder attribute
        4. title attribute
        5. alt attribute (for images)

        Args:
            element: Playwright ElementHandle

        Returns:
            Accessible name string
        """
        # Try aria-label
        name = element.evaluate("el => el.getAttribute('aria-label')")
        if name:
            return name

        # Try text content
        name = element.evaluate("""
            el => {
                const text = el.textContent?.trim();
                return text ? text.substring(0, 50) : '';
            }
        """)
        if name:
            return name

        # Try placeholder
        name = element.evaluate("el => el.getAttribute('placeholder')")
        if name:
            return name

        # Try title
        name = element.evaluate("el => el.getAttribute('title')")
        if name:
            return name

        # Try alt (for images)
        name = element.evaluate("el => el.getAttribute('alt')")
        if name:
            return name

        return ""

    @classmethod
    def is_interactive(cls, role: str) -> bool:
        """Check if role represents an interactive element

        Args:
            role: ARIA role

        Returns:
            True if role is interactive
        """
        return role.lower() in INTERACTIVE_ROLES
