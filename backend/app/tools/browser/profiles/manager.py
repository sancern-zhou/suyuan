"""Profile Manager

Manages browser profiles for multi-user isolation.
"""
import os
import shutil
import structlog
from typing import Dict, Optional, List
from dataclasses import replace

from .config import ProfileConfig, BrowserProfile
from .driver import ProfileDriver

logger = structlog.get_logger()


class ProfileManager:
    """Browser profile manager

    Manages multiple browser profiles with isolated user data directories.
    Supports 10-20 concurrent profiles.
    """

    def __init__(self, config: Optional[ProfileConfig] = None):
        """Initialize profile manager

        Args:
            config: Profile configuration (uses defaults if None)
        """
        self.config = config or ProfileConfig()
        self.profiles: Dict[str, BrowserProfile] = {}
        self._ensure_profiles_dir()
        self._create_default_profiles()

    def _ensure_profiles_dir(self):
        """Ensure profiles directory exists"""
        os.makedirs(self.config.profiles_dir, exist_ok=True)
        logger.info("[PROFILE_MANAGER] Profiles directory ensured", path=self.config.profiles_dir)

    def _create_default_profiles(self):
        """Create default profiles"""
        for name in self.config.default_profiles:
            if name not in self.profiles:
                profile_dir = self.config.get_profile_dir(name)
                os.makedirs(profile_dir, exist_ok=True)

                self.profiles[name] = BrowserProfile(
                    name=name,
                    user_data_dir=profile_dir,
                    is_default=(name == "default"),
                    color=self.config.get_profile_color(name)
                )

                logger.info(
                    "[PROFILE_MANAGER] Default profile created",
                    name=name,
                    directory=profile_dir
                )

    def get_profile(self, name: str) -> Optional[BrowserProfile]:
        """Get profile by name

        Args:
            name: Profile name

        Returns:
            BrowserProfile if found, None otherwise
        """
        return self.profiles.get(name)

    def create_profile(
        self,
        name: str,
        color: Optional[str] = None,
        is_remote: bool = False,
        cdp_port: Optional[int] = None
    ) -> BrowserProfile:
        """Create new profile

        Args:
            name: Profile name (must be unique)
            color: Profile color
            is_remote: Whether this is a remote profile
            cdp_port: CDP port for remote profiles

        Returns:
            Created BrowserProfile

        Raises:
            ValueError: If profile already exists
        """
        if name in self.profiles:
            raise ValueError(f"Profile {name} already exists")

        if len(self.profiles) >= self.config.max_profiles:
            raise ValueError(f"Maximum number of profiles ({self.config.max_profiles}) reached")

        profile_dir = self.config.get_profile_dir(name)
        os.makedirs(profile_dir, exist_ok=True)

        profile = BrowserProfile(
            name=name,
            user_data_dir=profile_dir,
            color=color or self.config.get_profile_color(name),
            is_remote=is_remote,
            cdp_port=cdp_port
        )

        self.profiles[name] = profile

        logger.info(
            "[PROFILE_MANAGER] Profile created",
            name=name,
            directory=profile_dir,
            total_profiles=len(self.profiles)
        )

        return profile

    def delete_profile(self, name: str) -> bool:
        """Delete profile

        Args:
            name: Profile name

        Returns:
            True if deleted, False if not found
        """
        if name not in self.profiles:
            return False

        profile = self.profiles[name]

        # Don't allow deleting default profile
        if profile.is_default:
            raise ValueError("Cannot delete default profile")

        # Stop profile if running
        if profile.running:
            logger.warning("[PROFILE_MANAGER] Cannot delete running profile", name=name)
            return False

        # Delete data directory
        if os.path.exists(profile.user_data_dir):
            shutil.rmtree(profile.user_data_dir)
            logger.info("[PROFILE_MANAGER] Profile data deleted", directory=profile.user_data_dir)

        del self.profiles[name]

        logger.info(
            "[PROFILE_MANAGER] Profile deleted",
            name=name,
            remaining_profiles=len(self.profiles)
        )

        return True

    def list_profiles(self) -> Dict[str, Dict]:
        """List all profiles

        Returns:
            Dictionary of profile information
        """
        return {
            name: {
                "name": p.name,
                "color": p.color,
                "is_default": p.is_default,
                "is_remote": p.is_remote,
                "running": p.running,
                "user_data_dir": p.user_data_dir,
                "cdp_port": p.cdp_port
            }
            for name, p in self.profiles.items()
        }

    def get_default_profile(self) -> BrowserProfile:
        """Get default profile

        Returns:
            Default BrowserProfile
        """
        for profile in self.profiles.values():
            if profile.is_default:
                return profile

        # Fallback to first profile if no default marked
        if self.profiles:
            return next(iter(self.profiles.values()))

        # Create default if none exist
        return self.create_profile("default", is_default=True)

    def set_profile_running(self, name: str, running: bool):
        """Set profile running state

        Args:
            name: Profile name
            running: Running state
        """
        if name in self.profiles:
            self.profiles[name].running = running
            logger.info(
                "[PROFILE_MANAGER] Profile state updated",
                name=name,
                running=running
            )
