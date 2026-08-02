# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from warestore.infrastructure.persistence import (
    AccountMetadataRepository,
    HwidProfileRepository,
    SettingsRepository,
    TokenRepository,
)
from warestore.domain.accounts.services.token_parser import TokenParser
from warestore.domain.auth.jwt_service import SteamJwtService
from warestore.domain.steam.services.login_service import SteamLoginService
from warestore.infrastructure.external.update_gateway import UpdateGateway
from warestore.infrastructure.steam.api_key_gateway import SteamApiKeyGateway
from warestore.infrastructure.steam.bans_gateway import SteamBansGateway
from warestore.infrastructure.steam.cs2_config_gateway import Cs2ConfigGateway
from warestore.infrastructure.steam.crypto_gateway import SteamCryptoGateway
from warestore.infrastructure.steam.gcpd_scrape_gateway import Cs2RankScrapeGateway
from warestore.infrastructure.steam.level_gateway import SteamLevelGateway
from warestore.infrastructure.steam.persona_gateway import PersonaGateway
from warestore.infrastructure.steam.process_gateway import SteamProcessGateway
from warestore.infrastructure.steam.profile_gateway import SteamProfileGateway
from warestore.infrastructure.steam.registry_gateway import SteamRegistryGateway
from warestore.infrastructure.steam.summaries_gateway import SteamSummariesGateway
from warestore.infrastructure.steam.userdata_gateway import UserdataGateway
from warestore.infrastructure.steam.vdf_file_gateway import VdfFileGateway


class AccountManagerFacade:
    """Composition root for account-manager application services."""

    def __init__(self, vault_key: bytes | None = None) -> None:
        self.settings = SettingsRepository()
        self.metadata = AccountMetadataRepository()
        self.tokens = TokenRepository(key=vault_key)
        self.hwid_profiles = HwidProfileRepository()
        self.parser = TokenParser()
        self.jwt = SteamJwtService()
        self.profiles = SteamProfileGateway()
        self.summaries = SteamSummariesGateway()
        self.bans = SteamBansGateway()
        self.levels = SteamLevelGateway()
        self.cs2_rank = Cs2RankScrapeGateway()
        self.api_key = SteamApiKeyGateway()
        self.cs2_config = Cs2ConfigGateway()
        self.userdata = UserdataGateway()
        self.steam_login = SteamLoginService(
            process=SteamProcessGateway(),
            files=VdfFileGateway(),
            crypto=SteamCryptoGateway(),
            registry=SteamRegistryGateway(),
            persona=PersonaGateway(),
            tokens=self.tokens,
            jwt=self.jwt,
            parser=self.parser,
        )
        self.updates = UpdateGateway()
