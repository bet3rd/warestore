# Changelog

All notable changes to WareStore are documented here. Release notes also appear
in the in-app updater and on the
[Releases](https://github.com/bet3rd/warestore/releases) page.

## 3.3.0

**New features**

- **Accounts** — redesigned account cards: a compact portrait grid that shows
  each account's CS2 rank, competitive cooldown, and online status at a glance.
- **CS2** — on-demand Premier and Wingman ranks plus competitive-cooldown
  status, fetched directly from Steam. The web session is minted in-process, so
  nothing extra is bundled or run in the background.
- **CS2** — fetch ranks for every account (a toolbar button next to refresh),
  for a multi-selection, or automatically on launch. Fetches run one account at
  a time so they never hammer Steam.
- **CS2** — Premier and Wingman win counts now appear in the card tooltip.

**Bug fixes**

- **Accounts** — online and in-game statuses now use distinct colors.
- **Accounts** — expired tokens are removed reliably, and accounts left without
  a token are cleaned up.
- **CS2** — cooldown display is consistent: a coarse label on the card, full
  detail in the tooltip.
