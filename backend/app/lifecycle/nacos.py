"""Nacos naming lifecycle for the Suyuan gateway upstream."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import structlog
from v2.nacos import (
    ClientConfigBuilder,
    DeregisterInstanceParam,
    NacosNamingService,
    RegisterInstanceParam,
)

from config.settings import Settings, settings


logger = structlog.get_logger(__name__)
NamingFactory = Callable[[Any], Awaitable[Any]]


class NacosLifecycle:
    def __init__(
        self,
        config: Settings,
        *,
        naming_factory: NamingFactory | None = None,
    ) -> None:
        self.config = config
        self._naming_factory = (
            naming_factory or NacosNamingService.create_naming_service
        )
        self._client: Any | None = None
        self._registered = False

    async def start(self, app: Any) -> None:
        app.state.nacos_ready = False
        app.state.nacos_status = {"enabled": self.config.nacos_register_enabled}
        if not self.config.nacos_register_enabled:
            app.state.nacos_status["state"] = "disabled"
            return

        try:
            client_config = self._build_client_config()
            self._client = await self._naming_factory(client_config)
            registered = await self._client.register_instance(self._register_request())
            if not registered:
                raise RuntimeError("Nacos rejected service registration")
            self._registered = True
            app.state.nacos_ready = True
            app.state.nacos_status = {
                "enabled": True,
                "state": "registered",
                "namespace": self.config.nacos_namespace,
                "group": self.config.nacos_group,
                "service": self.config.nacos_service_name,
            }
            logger.info("nacos_instance_registered", **app.state.nacos_status)
        except Exception as exc:
            app.state.nacos_status = {
                "enabled": True,
                "state": "failed",
                "error_type": type(exc).__name__,
            }
            logger.error("nacos_registration_failed", error_type=type(exc).__name__)
            if self._client is not None:
                await self._shutdown_client()
            if self.config.environment.strip().lower() == "production":
                raise

    async def stop(self, app: Any) -> None:
        if self._client is None:
            app.state.nacos_ready = False
            return
        try:
            if self._registered:
                await self._client.deregister_instance(self._deregister_request())
                self._registered = False
                logger.info("nacos_instance_deregistered")
        finally:
            await self._shutdown_client()
            app.state.nacos_ready = False

    async def _shutdown_client(self) -> None:
        """Best-effort close for clients whose internal stop may be non-awaitable."""
        client = self._client
        if client is None:
            return
        try:
            await client.shutdown()
        except Exception as exc:
            logger.warning(
                "nacos_client_shutdown_failed",
                error_type=type(exc).__name__,
            )
        finally:
            self._client = None

    def _build_client_config(self):
        builder = (
            ClientConfigBuilder()
            .server_address(",".join(self.config.nacos_server_addresses_list))
            .namespace_id(self.config.nacos_namespace)
        )
        if self.config.nacos_username:
            builder.username(self.config.nacos_username)
        if self.config.nacos_password:
            builder.password(self.config.nacos_password)
        if self.config.nacos_access_key:
            builder.access_key(self.config.nacos_access_key)
        if self.config.nacos_secret_key:
            builder.secret_key(self.config.nacos_secret_key)
        return builder.build()

    def _register_request(self) -> RegisterInstanceParam:
        return RegisterInstanceParam(
            ip=self.config.nacos_instance_ip,
            port=self.config.nacos_instance_port,
            enabled=self.config.nacos_instance_enabled,
            healthy=True,
            metadata={
                "system": "Suyuan",
                "service": self.config.nacos_service_name,
                "sysCode": self.config.auth_sys_code,
            },
            cluster_name=self.config.nacos_cluster_name,
            service_name=self.config.nacos_service_name,
            group_name=self.config.nacos_group,
            ephemeral=True,
        )

    def _deregister_request(self) -> DeregisterInstanceParam:
        return DeregisterInstanceParam(
            ip=self.config.nacos_instance_ip,
            port=self.config.nacos_instance_port,
            cluster_name=self.config.nacos_cluster_name,
            service_name=self.config.nacos_service_name,
            group_name=self.config.nacos_group,
            ephemeral=True,
        )


async def start_nacos(app: Any, config: Settings = settings) -> None:
    lifecycle = NacosLifecycle(config)
    app.state.nacos_lifecycle = lifecycle
    await lifecycle.start(app)


async def stop_nacos(app: Any) -> None:
    lifecycle = getattr(app.state, "nacos_lifecycle", None)
    if lifecycle is not None:
        await lifecycle.stop(app)
