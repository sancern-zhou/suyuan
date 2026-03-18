"""Unit tests for Smart Reference System

Tests RoleRef, AriaRef, CssRef, and RefResolver functionality.
"""
import pytest
from app.tools.browser.refs.role_ref import RoleRef, INTERACTIVE_ROLES
from app.tools.browser.refs.aria_ref import AriaRef
from app.tools.browser.refs.css_ref import CssRef
from app.tools.browser.refs.resolver import RefResolver


class TestRoleRef:
    """Test RoleRef functionality"""

    def test_role_ref_creation(self):
        """Test creating RoleRef instance"""
        ref = RoleRef(element_id="e1", role="button", name="Login")
        assert ref.element_id == "e1"
        assert ref.role == "button"
        assert ref.name == "Login"

    def test_role_ref_string_representation(self):
        """Test string representation"""
        ref = RoleRef(element_id="e1", role="button", name="Login")
        assert str(ref) == '[e1] button: "Login"'

        ref_no_name = RoleRef(element_id="e2", role="textbox")
        assert str(ref_no_name) == "[e2] textbox"

    def test_role_ref_with_index(self):
        """Test RoleRef with index"""
        ref = RoleRef(element_id="e1", role="button")
        ref_with_index = ref.with_index(2)
        assert ref_with_index is ref  # Returns self

    def test_interactive_roles(self):
        """Test interactive role detection"""
        assert RoleRef.is_interactive("button") == True
        assert RoleRef.is_interactive("textbox") == True
        assert RoleRef.is_interactive("link") == True
        assert RoleRef.is_interactive("article") == False
        assert RoleRef.is_interactive("generic") == False

    def test_input_role_mapping(self):
        """Test input type to role mapping"""
        assert RoleRef._get_input_role("text") == "textbox"
        assert RoleRef._get_input_role("password") == "textbox"
        assert RoleRef._get_input_role("checkbox") == "checkbox"
        assert RoleRef._get_input_role("radio") == "radio"
        assert RoleRef._get_input_role("submit") == "button"
        assert RoleRef._get_input_role("search") == "searchbox"
        assert RoleRef._get_input_role("range") == "slider"


class TestAriaRef:
    """Test AriaRef functionality"""

    def test_aria_ref_creation(self):
        """Test creating AriaRef instance"""
        ref = AriaRef(element_id="aria:e1", aria_label="Close", aria_role="button")
        assert ref.element_id == "aria:e1"
        assert ref.aria_label == "Close"
        assert ref.aria_role == "button"

    def test_aria_ref_string_representation(self):
        """Test string representation"""
        ref = AriaRef(element_id="aria:e1", aria_label="Close", aria_role="button")
        result = str(ref)
        assert "aria:e1" in result
        assert "role=button" in result
        assert 'label="Close"' in result

        ref_minimal = AriaRef(element_id="aria:e2")
        assert str(ref_minimal) == "[aria:e2]"


class TestCssRef:
    """Test CssRef functionality"""

    def test_css_ref_creation(self):
        """Test creating CssRef instance"""
        ref = CssRef(element_id="css:submit", selector="#submit-btn")
        assert ref.element_id == "css:submit"
        assert ref.selector == "#submit-btn"

    def test_css_ref_string_representation(self):
        """Test string representation"""
        ref = CssRef(element_id="css:submit", selector="#submit-btn")
        assert str(ref) == "[css:submit] #submit-btn"


class TestRefResolver:
    """Test RefResolver functionality"""

    def test_detect_role_ref(self):
        """Test Role reference type detection"""
        assert RefResolver.detect_ref_type("e1") == "role"
        assert RefResolver.detect_ref_type("e100") == "role"
        assert RefResolver.detect_ref_type("e999") == "role"

    def test_detect_aria_ref(self):
        """Test ARIA reference type detection"""
        assert RefResolver.detect_ref_type("aria:e1") == "aria"
        assert RefResolver.detect_ref_type("aria:e100") == "aria"

    def test_detect_css_ref(self):
        """Test CSS reference type detection"""
        assert RefResolver.detect_ref_type("#submit-btn") == "css"
        assert RefResolver.detect_ref_type(".btn-primary") == "css"
        assert RefResolver.detect_ref_type("button") == "css"
        assert RefResolver.detect_ref_type('input[type="submit"]') == "css"

    def test_validate_ref(self):
        """Test reference validation"""
        # Valid refs
        assert RefResolver.validate_ref("e1") == True
        assert RefResolver.validate_ref("aria:e1") == True
        assert RefResolver.validate_ref("#submit-btn") == True
        assert RefResolver.validate_ref(".btn") == True
        assert RefResolver.validate_ref("button") == True

        # Invalid refs
        assert RefResolver.validate_ref("invalid:not-a-ref") == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
