"""Unit tests for Profile Management System

Tests ProfileManager, ProfileConfig, and ProfileDriver functionality.
"""
import pytest
import os
import tempfile
import shutil
from app.tools.browser.profiles.config import ProfileConfig, BrowserProfile
from app.tools.browser.profiles.manager import ProfileManager


class TestProfileConfig:
    """Test ProfileConfig functionality"""

    def test_config_creation(self):
        """Test creating ProfileConfig instance"""
        config = ProfileConfig()
        assert config.profiles_dir == "backend_data_registry/browser_profiles"
        assert config.max_profiles == 20
        assert "default" in config.default_profiles

    def test_get_profile_color(self):
        """Test get_profile_color returns correct colors"""
        config = ProfileConfig()
        assert config.get_profile_color("default") == "#FF4500"
        assert config.get_profile_color("chrome") == "#00AA00"
        assert config.get_profile_color("unknown") == "#007AFF"  # Default

    def test_get_profile_dir(self):
        """Test get_profile_dir returns correct path"""
        config = ProfileConfig()
        dir_path = config.get_profile_dir("test")
        assert "test" in dir_path
        assert config.profiles_dir in dir_path


class TestBrowserProfile:
    """Test BrowserProfile functionality"""

    def test_profile_creation(self):
        """Test creating BrowserProfile instance"""
        profile = BrowserProfile(
            name="test",
            user_data_dir="/tmp/test_profile",
            color="#FF0000"
        )
        assert profile.name == "test"
        assert profile.user_data_dir == "/tmp/test_profile"
        assert profile.color == "#FF0000"
        assert profile.is_default == False
        assert profile.running == False

    def test_get_launch_args(self):
        """Test get_launch_args returns correct arguments"""
        profile = BrowserProfile(
            name="test",
            user_data_dir="/tmp/test_profile"
        )
        args = profile.get_launch_args()
        assert args["user_data_dir"] == "/tmp/test_profile"
        assert args["headless"] == False

    def test_get_launch_args_with_cdp(self):
        """Test get_launch_args with CDP port"""
        profile = BrowserProfile(
            name="test",
            user_data_dir="/tmp/test_profile",
            cdp_port=9222
        )
        args = profile.get_launch_args()
        assert "--remote-debugging-port=9222" in args["args"]


class TestProfileManager:
    """Test ProfileManager functionality"""

    @pytest.fixture
    def temp_profile_dir(self):
        """Create temporary directory for profiles"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def manager(self, temp_profile_dir):
        """Create ProfileManager with temporary directory"""
        config = ProfileConfig(profiles_dir=temp_profile_dir, default_profiles=["default"])
        return ProfileManager(config)

    def test_manager_creation(self, manager):
        """Test creating ProfileManager instance"""
        assert manager is not None
        assert len(manager.profiles) == 1
        assert "default" in manager.profiles

    def test_get_profile(self, manager):
        """Test get_profile returns correct profile"""
        profile = manager.get_profile("default")
        assert profile is not None
        assert profile.name == "default"
        assert profile.is_default == True

    def test_create_profile(self, manager):
        """Test creating new profile"""
        profile = manager.create_profile("test_profile", color="#00FF00")
        assert profile.name == "test_profile"
        assert profile.color == "#00FF00"
        assert "test_profile" in manager.profiles

    def test_create_duplicate_profile_raises_error(self, manager):
        """Test creating duplicate profile raises error"""
        manager.create_profile("test")
        with pytest.raises(ValueError) as exc_info:
            manager.create_profile("test")
        assert "already exists" in str(exc_info.value)

    def test_delete_profile(self, manager):
        """Test deleting profile"""
        manager.create_profile("test_delete")
        result = manager.delete_profile("test_delete")
        assert result == True
        assert "test_delete" not in manager.profiles

    def test_delete_default_profile_raises_error(self, manager):
        """Test deleting default profile raises error"""
        with pytest.raises(ValueError) as exc_info:
            manager.delete_profile("default")
        assert "Cannot delete default profile" in str(exc_info.value)

    def test_delete_nonexistent_profile_returns_false(self, manager):
        """Test deleting nonexistent profile returns False"""
        result = manager.delete_profile("nonexistent")
        assert result == False

    def test_list_profiles(self, manager):
        """Test listing profiles"""
        manager.create_profile("profile1")
        manager.create_profile("profile2")

        profiles = manager.list_profiles()
        assert len(profiles) == 3  # default + profile1 + profile2
        assert "default" in profiles
        assert "profile1" in profiles
        assert "profile2" in profiles

    def test_get_default_profile(self, manager):
        """Test getting default profile"""
        profile = manager.get_default_profile()
        assert profile is not None
        assert profile.is_default == True

    def test_set_profile_running(self, manager):
        """Test setting profile running state"""
        manager.set_profile_running("default", True)
        profile = manager.get_profile("default")
        assert profile.running == True

        manager.set_profile_running("default", False)
        profile = manager.get_profile("default")
        assert profile.running == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
