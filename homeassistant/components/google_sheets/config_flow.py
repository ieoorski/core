"""Config flow for Google Sheets integration."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from gspread import Client, GSpreadException

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TOKEN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DEFAULT_ACCESS, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Google Sheets OAuth2 authentication."""

    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": DEFAULT_ACCESS,
            # Add params to ensure we get back a refresh token
            "access_type": "offline",
            "prompt": "consent",
        }

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm reauth dialog."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    def _async_reauth_entry(self) -> ConfigEntry | None:
        """Return existing entry for reauth."""
        if self.source != SOURCE_REAUTH or not (
            entry_id := self.context.get("entry_id")
        ):
            return None
        return next(
            (
                entry
                for entry in self._async_current_entries()
                if entry.entry_id == entry_id
            ),
            None,
        )

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> FlowResult:
        """Create an entry for the flow, or update existing entry."""
        service = Client(Credentials(data[CONF_TOKEN][CONF_ACCESS_TOKEN]))

        if entry := self._async_reauth_entry():
            _LOGGER.debug("service.open_by_key")
            try:
                await self.hass.async_add_executor_job(
                    service.open_by_key,
                    entry.unique_id,
                )
            except GSpreadException as err:
                _LOGGER.error(
                    "Could not find spreadsheet '%s': %s", entry.unique_id, str(err)
                )
                return self.async_abort(reason="open_spreadsheet_failure")

            self.hass.config_entries.async_update_entry(entry, data=data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        try:
            doc = await self.hass.async_add_executor_job(
                service.create, "Home Assistant"
            )
        except GSpreadException as err:
            _LOGGER.error("Error creating spreadsheet: %s", str(err))
            return self.async_abort(reason="create_spreadsheet_failure")

        await self.async_set_unique_id(doc.id)
        return self.async_create_entry(
            title=DEFAULT_NAME, data=data, description_placeholders={"url": doc.url}
        )
