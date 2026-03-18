"""Profile Configuration

Defines profile settings and defaults.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, List


@dataclass
class BrowserProfile:
    """Browser profile configuration

    Attributes:
        name: Profile name (unique identifier)
        user_data_dir: Path to user data directory
        color: Profile color for UI identification
        is_default: Whether this is the default profile
        is_remote: Whether this is a remote profile (CDP)
        cdp_port: CDP port for remote profiles
        running: Whether the profile is currently running
    """
    name: str
    user_data_dir: str
    color: str = "#FF4500"
    is_default: bool = False
    is_remote: bool = False
    cdp_port: Optional[int] = None
    running: bool = False

    def get_launch_args(self) -> Dict:
        """Get launch arguments for this profile

        Returns:
            Dictionary of launch arguments
        """
        args = {
            "headless": False,
            "user_data_dir": self.user_data_dir,
        }

        if self.cdp_port:
            args["args"] = [f"--remote-debugging-port={self.cdp_port}"]

        return args


@dataclass
class ProfileConfig:
    """Profile management configuration

    Attributes:
        profiles_dir: Directory for profile data
        default_profiles: Default profile names
        max_profiles: Maximum number of profiles
        profile_colors: Color mapping for profiles
    """
    profiles_dir: str = "backend_data_registry/browser_profiles"
    default_profiles: List[str] = field(default_factory=lambda: ["default", "clawd", "chrome"])
    max_profiles: int = 20

    # Profile color mapping
    profile_colors: Dict[str, str] = field(default_factory=lambda: {
        "default": "#FF4500",  # Orange
        "clawd": "#FF4500",
        "chrome": "#00AA00",   # Green
        "work": "#007AFF",     # Blue
        "personal": "#FF3B30", # Red
        "testing": "#FFCC00",  # Yellow
    })

    def get_profile_color(self, name: str) -> str:
        """Get color for profile

        Args:
            name: Profile name

        Returns:
            Color hex code
        """
        return self.profile_colors.get(name, "#007AFF")

    def get_profile_dir(self, name: str) -> str:
        """Get directory path for profile

        Args:
            name: Profile name

        Returns:
            Directory path
        """
        return os.path.join(self.profiles_dir, name)
