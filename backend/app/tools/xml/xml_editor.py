"""
XMLEditor - Secure XML DOM Editor

Provides secure XML manipulation with node location and editing capabilities.
Uses defusedxml for security against XML attacks.

Features:
- Node location by tag, attributes, line number, text content
- Node operations: replace, insert_after, insert_before, append_to
- Line number tracking for precise editing
- Secure XML parsing with defusedxml.minidom
- RSID and metadata auto-injection for Word documents
"""

import random
from typing import List, Optional, Dict, Any, Union
from defusedxml import minidom
import structlog

logger = structlog.get_logger()


def _generate_hex_id() -> str:
    """
    Generate random 8-character hex ID for Word document identifiers.

    Values are constrained to be less than 0x7FFFFFFF per OOXML spec.
    Used for paraId and durableId attributes.
    """
    return f"{random.randint(1, 0x7FFFFFFE):08X}"


def _generate_rsid() -> str:
    """
    Generate random 8-character hex RSID (Revision Save ID).

    RSIDs are used by Word to track document revision history.
    """
    return "".join(random.choices("0123456789ABCDEF", k=8))


class XMLNode:
    """
    Wrapper for XML DOM nodes with line number tracking.

    Provides convenient access to node properties and enables
    precise location and manipulation of XML elements.
    """

    def __init__(self, dom_node, line_number: Optional[int] = None):
        """
        Initialize XMLNode wrapper.

        Args:
            dom_node: The underlying minidom node object
            line_number: Original line number in source file (if available)
        """
        self._node = dom_node
        self._line_number = line_number

    @property
    def tag_name(self) -> str:
        """Get the tag name of the node."""
        return self._node.tagName if hasattr(self._node, 'tagName') else ''

    @property
    def text(self) -> str:
        """
        Get the text content of the node (recursively).

        For Word documents, this correctly handles nested structures like:
        <w:p><w:r><w:t>text</w:t></w:r></w:p>

        Returns:
            The concatenated text content from all descendant text nodes.
        """
        if self._node.nodeType == self._node.TEXT_NODE:
            return self._node.nodeValue or ''

        # Recursively extract text from all descendant nodes
        return self._extract_text_recursive(self._node)

    def _extract_text_recursive(self, node) -> str:
        """
        Recursively extract text content from a DOM node and its descendants.

        This correctly handles Word document XML structure where text is nested
        inside <w:r><w:t> elements within paragraph <w:p> elements.

        Args:
            node: A minidom DOM node

        Returns:
            Concatenated text from all text nodes in the subtree
        """
        texts = []
        for child in node.childNodes:
            if child.nodeType == child.TEXT_NODE:
                text = child.nodeValue or ''
                # Skip whitespace-only nodes (XML formatting)
                if text.strip():
                    texts.append(text)
                else:
                    # Keep meaningful whitespace
                    texts.append(text)
            elif child.nodeType == child.ELEMENT_NODE:
                # Recursively process element children
                texts.append(self._extract_text_recursive(child))
        return ''.join(texts)

    @property
    def attributes(self) -> Dict[str, str]:
        """Get all attributes as a dictionary."""
        if not hasattr(self._node, 'attributes'):
            return {}
        attrs = {}
        for i in range(self._node.attributes.length):
            attr = self._node.attributes.item(i)
            attrs[attr.name] = attr.value
        return attrs

    @property
    def line_number(self) -> Optional[int]:
        """Get the original line number of this node."""
        return self._line_number

    @property
    def children(self) -> List['XMLNode']:
        """Get child nodes as XMLNode objects."""
        return [
            XMLNode(child)
            for child in self._node.childNodes
            if child.nodeType == child.ELEMENT_NODE
        ]

    def get_attribute(self, name: str) -> Optional[str]:
        """Get a specific attribute value."""
        return self.attributes.get(name)

    def to_xml(self) -> str:
        """Convert node back to XML string."""
        return self._node.toxml()

    def __repr__(self) -> str:
        line_info = f":{self._line_number}" if self._line_number else ""
        return f"XMLNode({self.tag_name}{line_info})"


class XMLEditor:
    """
    Secure XML DOM editor with advanced node location and manipulation.

    Provides a safe and powerful way to edit XML documents,
    particularly useful for Office document XML manipulation.

    Example:
        editor = XMLEditor(xml_content)

        # Find nodes by tag
        nodes = editor.get_nodes(tag="w:p")

        # Find nodes containing specific text
        nodes = editor.get_nodes(tag="w:p", contains="目标文本")

        # Find nodes by attribute
        nodes = editor.get_nodes(tag="w:pStyle", attributes={"w:val": "1"})

        # Replace a node
        editor.replace_node(nodes[0], "<w:p>New content</w:p>")

        # Get modified XML
        new_xml = editor.to_xml()
    """

    def __init__(self, xml_content: str, enable_rsid: bool = False, author: str = "Claude"):
        """
        Initialize XMLEditor with XML content.

        Args:
            xml_content: The XML content as a string
            enable_rsid: Enable RSID auto-injection for Word documents (default False)
            author: Author name for tracked changes (default "Claude")
        """
        self._original_content = xml_content
        self._doc = minidom.parseString(xml_content)
        self._line_map = self._build_line_map(xml_content)
        self._enable_rsid = enable_rsid
        self._author = author
        self._rsid = _generate_rsid() if enable_rsid else None
        self._next_change_id = 0

    def _build_line_map(self, content: str) -> Dict[int, int]:
        """
        Build a map of node positions to line numbers.

        Args:
            content: The original XML content

        Returns:
            Dictionary mapping character positions to line numbers
        """
        line_map = {0: 1}
        line_num = 1
        for i, char in enumerate(content):
            if char == '\n':
                line_num += 1
                line_map[i + 1] = line_num
        return line_map

    def _get_line_number(self, position: int) -> Optional[int]:
        """
        Get line number for a character position.

        Args:
            position: Character position in the original content

        Returns:
            Line number (1-based) or None if not found
        """
        if not self._line_map:
            return None

        # Find the largest key <= position
        keys = [k for k in self._line_map.keys() if k <= position]
        if not keys:
            return None
        return self._line_map[max(keys)]

    def get_nodes(
        self,
        tag: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
        contains: Optional[str] = None,
        line_number: Optional[int] = None
    ) -> List[XMLNode]:
        """
        Find XML nodes matching the given criteria.

        Args:
            tag: Tag name to match (e.g., "w:p", "w:t")
            attributes: Attribute name-value pairs to match
            contains: Text content that nodes must contain
            line_number: Specific line number to match

        Returns:
            List of XMLNode objects matching all criteria

        Examples:
            # Get all paragraphs
            editor.get_nodes(tag="w:p")

            # Get paragraphs with specific style
            editor.get_nodes(tag="w:p", attributes={"w:pStyle": "Heading1"})

            # Get paragraphs containing text
            editor.get_nodes(tag="w:p", contains="关键词")

            # Get element at specific line
            editor.get_nodes(line_number=42)
        """
        nodes = []

        # Get starting node collection
        if tag:
            dom_nodes = self._doc.getElementsByTagName(tag)
        else:
            dom_nodes = [self._doc.documentElement]

        # Filter by criteria
        for dom_node in dom_nodes:
            # Wrap node
            node = XMLNode(dom_node)

            # Filter by attributes
            if attributes:
                match = True
                for attr_name, attr_value in attributes.items():
                    if node.get_attribute(attr_name) != attr_value:
                        match = False
                        break
                if not match:
                    continue

            # Filter by text content
            if contains and contains not in node.text:
                continue

            # Filter by line number
            if line_number is not None and node.line_number != line_number:
                continue

            nodes.append(node)

        return nodes

    def find_text_location(self, search_text: str, tag: str = "w:t") -> List[XMLNode]:
        """
        Find text nodes containing specific text.

        Convenience method for finding text nodes in Word documents.

        Args:
            search_text: Text to search for
            tag: Tag name for text elements (default: "w:t")

        Returns:
            List of XMLNode objects containing the search text
        """
        all_text_nodes = self.get_nodes(tag=tag)
        return [node for node in all_text_nodes if search_text in node.text]

    def get_node(
        self,
        tag: str,
        attrs: Optional[Dict[str, str]] = None,
        line_number: Optional[Union[int, range]] = None,
        contains: Optional[str] = None,
    ) -> XMLNode:
        """
        Get a single DOM element by tag and identifier.

        Finds an element by tag name with optional filters. Exactly one match
        must be found, otherwise raises ValueError.

        Args:
            tag: The XML tag name (e.g., "w:del", "w:ins", "w:r", "w:p")
            attrs: Dictionary of attribute name-value pairs to match (e.g., {"w:id": "1"})
            line_number: Line number (int) or line range (range) in original XML file
            contains: Text string that must appear in the element's text content

        Returns:
            XMLNode: The matching node

        Raises:
            ValueError: If node not found or multiple matches found

        Example:
            elem = editor.get_node(tag="w:p", contains="O3区县分布特征")
            elem = editor.get_node(tag="w:del", attrs={"w:id": "1"})
            elem = editor.get_node(tag="w:p", line_number=42)
        """
        nodes = self.get_nodes(tag=tag, attributes=attrs, contains=contains)

        # Filter by line_number if specified
        if line_number is not None:
            filtered_nodes = []
            for node in nodes:
                node_line = node.line_number
                if isinstance(line_number, range):
                    if node_line in line_number:
                        filtered_nodes.append(node)
                else:
                    if node_line == line_number:
                        filtered_nodes.append(node)
            nodes = filtered_nodes

        if not nodes:
            # Build descriptive error message
            filters = []
            if line_number is not None:
                line_str = (
                    f"lines {line_number.start}-{line_number.stop - 1}"
                    if isinstance(line_number, range)
                    else f"line {line_number}"
                )
                filters.append(f"at {line_str}")
            if attrs:
                filters.append(f"with attributes {attrs}")
            if contains:
                filters.append(f"containing '{contains}'")

            filter_desc = " ".join(filters) if filters else ""
            base_msg = f"Node not found: <{tag}> {filter_desc}".strip()

            # Add helpful hint
            if contains:
                hint = "Text may be split across elements or use different wording."
            elif line_number:
                hint = "Line numbers may have changed if document was modified."
            elif attrs:
                hint = "Verify attribute values are correct."
            else:
                hint = "Try adding filters (attrs, line_number, or contains)."

            raise ValueError(f"{base_msg}. {hint}")

        if len(nodes) > 1:
            raise ValueError(
                f"Multiple nodes found: <{tag}> ({len(nodes)} matches). "
                f"Add more filters to narrow the search."
            )

        return nodes[0]

    # ==================== RSID and Attribute Injection ====================

    def _ensure_namespace(self, ns_prefix: str, ns_uri: str) -> None:
        """
        Ensure a namespace declaration exists on the root element.

        Args:
            ns_prefix: Namespace prefix (e.g., "w14")
            ns_uri: Namespace URI (e.g., "http://schemas.microsoft.com/office/word/2010/wordml")
        """
        root = self._doc.documentElement
        attr_name = f"xmlns:{ns_prefix}"
        if not root.hasAttribute(attr_name):
            root.setAttribute(attr_name, ns_uri)

    def _get_next_change_id(self) -> int:
        """Get the next available change ID for tracked changes."""
        max_id = -1
        for tag in ("w:ins", "w:del"):
            elements = self._doc.getElementsByTagName(tag)
            for elem in elements:
                change_id = elem.getAttribute("w:id")
                if change_id:
                    try:
                        max_id = max(max_id, int(change_id))
                    except ValueError:
                        pass
        return max_id + 1

    def _inject_attributes_to_nodes(self, dom_nodes) -> None:
        """
        Inject RSID and other attributes into DOM nodes for Word documents.

        Adds attributes to elements that support them:
        - w:p: gets w:rsidR, w:rsidRDefault, w:rsidP, w14:paraId, w14:textId
        - w:r: gets w:rsidR
        - w:t: gets xml:space="preserve" if text has leading/trailing whitespace
        - w:ins, w:del: get w:id, w:author, w:date, w16du:dateUtc

        This method is only called when enable_rsid=True in __init__.

        Args:
            dom_nodes: List of DOM nodes to process
        """
        if not self._enable_rsid:
            return

        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def is_inside_deletion(elem):
            """Check if element is inside a w:del element."""
            parent = elem.parentNode
            while parent:
                if parent.nodeType == parent.ELEMENT_NODE and parent.tagName == "w:del":
                    return True
                parent = parent.parentNode
            return False

        for node in dom_nodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue

            tag_name = node.tagName

            # Handle w:p (paragraph) elements
            if tag_name == "w:p":
                if not node.hasAttribute("w:rsidR"):
                    node.setAttribute("w:rsidR", self._rsid)
                if not node.hasAttribute("w:rsidRDefault"):
                    node.setAttribute("w:rsidRDefault", self._rsid)
                if not node.hasAttribute("w:rsidP"):
                    node.setAttribute("w:rsidP", self._rsid)
                # Add w14:paraId and w14:textId
                if not node.hasAttribute("w14:paraId"):
                    self._ensure_namespace("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
                    node.setAttribute("w14:paraId", _generate_hex_id())
                if not node.hasAttribute("w14:textId"):
                    self._ensure_namespace("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
                    node.setAttribute("w14:textId", _generate_hex_id())

            # Handle w:r (run) elements
            elif tag_name == "w:r":
                # Use w:rsidDel for runs inside w:del, otherwise w:rsidR
                if is_inside_deletion(node):
                    if not node.hasAttribute("w:rsidDel"):
                        node.setAttribute("w:rsidDel", self._rsid)
                else:
                    if not node.hasAttribute("w:rsidR"):
                        node.setAttribute("w:rsidR", self._rsid)

            # Handle w:t (text) elements - add xml:space for whitespace
            elif tag_name == "w:t":
                # Check if text has leading/trailing whitespace
                if node.firstChild and node.firstChild.nodeType == node.TEXT_NODE:
                    text = node.firstChild.data
                    if text and (text[0].isspace() or text[-1].isspace()):
                        if not node.hasAttribute("xml:space"):
                            node.setAttribute("xml:space", "preserve")

            # Handle w:ins and w:del (tracked changes)
            elif tag_name in ("w:ins", "w:del"):
                if not node.hasAttribute("w:id"):
                    node.setAttribute("w:id", str(self._get_next_change_id()))
                if not node.hasAttribute("w:author"):
                    node.setAttribute("w:author", self._author)
                if not node.hasAttribute("w:date"):
                    node.setAttribute("w:date", timestamp)
                # Add w16du:dateUtc for tracked changes
                if tag_name in ("w:ins", "w:del") and not node.hasAttribute("w16du:dateUtc"):
                    self._ensure_namespace("w16du", "http://schemas.microsoft.com/office/word/2023/wordml/word16du")
                    node.setAttribute("w16du:dateUtc", timestamp)

    def replace_node(self, node: XMLNode, new_xml: str) -> bool:
        """
        Replace a node with new XML content.

        Args:
            node: The XMLNode to replace
            new_xml: The new XML content as a string

        Returns:
            True if successful, False otherwise
        """
        try:
            # Parse the new XML with namespace handling
            new_nodes = self._parse_xml_fragment(new_xml)

            if not new_nodes:
                return False

            # Get the parent of the old node
            parent = node._node.parentNode

            if not parent:
                return False

            # Replace the old node with the first new node
            parent.replaceChild(new_nodes[0], node._node)

            # Insert any additional nodes after the first
            current = new_nodes[0]
            for additional_node in new_nodes[1:]:
                parent.insertBefore(additional_node.cloneNode(True), current.nextSibling)
                current = additional_node

            # Inject RSID and other attributes to newly inserted nodes
            self._inject_attributes_to_nodes(new_nodes)

            return True

        except Exception as e:
            logger.error("xml_node_replace_failed", error=str(e), node=node.tag_name, xml=new_xml[:100])
            return False

    def _parse_xml_fragment(self, xml_content: str) -> List:
        """
        Parse XML fragment with automatic namespace handling.

        Extracts namespace declarations from the root document and applies
        them to the fragment, ensuring proper XML parsing.

        Args:
            xml_content: String containing XML fragment

        Returns:
            List of DOM nodes imported into this document
        """
        # Extract namespace declarations from the root document element
        root_elem = self._doc.documentElement
        namespaces = []

        if root_elem and hasattr(root_elem, 'attributes'):
            for i in range(root_elem.attributes.length):
                attr = root_elem.attributes.item(i)
                if attr.name and attr.name.startswith("xmlns"):
                    namespaces.append(f'{attr.name}="{attr.value}"')

        ns_decl = " ".join(namespaces)
        wrapper = f"<root {ns_decl}>{xml_content}</root>"

        temp_doc = minidom.parseString(wrapper)
        nodes = []
        for child in temp_doc.documentElement.childNodes:
            if child.nodeType == child.ELEMENT_NODE:
                imported = self._doc.importNode(child, deep=True)
                nodes.append(imported)

        return nodes

    def insert_after(self, node: XMLNode, new_xml: str) -> bool:
        """
        Insert new XML content after a node.

        Args:
            node: The XMLNode to insert after
            new_xml: The new XML content as a string

        Returns:
            True if successful, False otherwise
        """
        try:
            new_nodes = self._parse_xml_fragment(new_xml)

            if not new_nodes:
                return False

            parent = node._node.parentNode
            if parent:
                # Insert all new nodes after the target
                current = node._node
                for new_node in new_nodes:
                    parent.insertBefore(new_node.cloneNode(True), current.nextSibling)
                    current = new_node

                # Inject RSID and other attributes to newly inserted nodes
                self._inject_attributes_to_nodes(new_nodes)
                return True

            return False

        except Exception as e:
            logger.error("xml_insert_after_failed", error=str(e))
            return False

    def insert_before(self, node: XMLNode, new_xml: str) -> bool:
        """
        Insert new XML content before a node.

        Args:
            node: The XMLNode to insert before
            new_xml: The new XML content as a string

        Returns:
            True if successful, False otherwise
        """
        try:
            new_nodes = self._parse_xml_fragment(new_xml)

            if not new_nodes:
                return False

            parent = node._node.parentNode
            if parent:
                # Insert all new nodes before the target (in reverse order)
                for new_node in reversed(new_nodes):
                    parent.insertBefore(new_node.cloneNode(True), node._node)

                # Inject RSID and other attributes to newly inserted nodes
                self._inject_attributes_to_nodes(new_nodes)
                return True

            return False

        except Exception as e:
            logger.error("xml_insert_before_failed", error=str(e))
            return False

    def append_to(self, node: XMLNode, new_xml: str) -> bool:
        """
        Append new XML content to a node's children.

        Args:
            node: The XMLNode to append to
            new_xml: The new XML content as a string

        Returns:
            True if successful, False otherwise
        """
        try:
            new_nodes = self._parse_xml_fragment(new_xml)

            if not new_nodes:
                return False

            # Append all new nodes to the target
            for new_node in new_nodes:
                node._node.appendChild(new_node.cloneNode(True))

            # Inject RSID and other attributes to newly appended nodes
            self._inject_attributes_to_nodes(new_nodes)
            return True

        except Exception as e:
            logger.error("xml_append_failed", error=str(e))
            return False

    def remove_node(self, node: XMLNode) -> bool:
        """
        Remove a node from the document.

        Args:
            node: The XMLNode to remove

        Returns:
            True if successful, False otherwise
        """
        try:
            parent = node._node.parentNode
            if parent:
                parent.removeChild(node._node)
                return True
            return False

        except Exception as e:
            logger.error("xml_remove_failed", error=str(e))
            return False

    def update_text(self, node: XMLNode, new_text: str) -> bool:
        """
        Update the text content of a node.

        This preserves the node structure and only updates text nodes within it.

        Args:
            node: The XMLNode to update
            new_text: The new text content

        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear existing text nodes
            text_nodes = [child for child in node._node.childNodes
                         if child.nodeType == child.TEXT_NODE]

            for text_node in text_nodes:
                node._node.removeChild(text_node)

            # Add new text
            if node._node.childNodes:
                node._node.insertBefore(
                    self._doc.createTextNode(new_text),
                    node._node.firstChild
                )
            else:
                node._node.appendChild(self._doc.createTextNode(new_text))

            return True

        except Exception as e:
            logger.error("xml_update_text_failed", error=str(e))
            return False

    def to_xml(self, pretty: bool = False) -> str:
        """
        Convert the document back to XML string.

        Args:
            pretty: Whether to pretty-print the output

        Returns:
            XML string representation of the document
        """
        if pretty:
            return self._doc.toprettyxml(indent="  ", encoding="utf-8").decode('utf-8')
        return self._doc.toxml(encoding='utf-8').decode('utf-8')

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the XML document.

        Returns:
            Dictionary with document statistics
        """
        return {
            "total_elements": len(self._doc.getElementsByTagName('*')),
            "root_tag": self._doc.documentElement.tagName,
            "has_line_map": len(self._line_map) > 0,
            "original_size": len(self._original_content),
        }
