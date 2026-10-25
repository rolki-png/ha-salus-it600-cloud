# Salus iT600 Cloud for Home Assistant

Home Assistant custom integration for Salus iT600 devices through the Salus Cloud API (EU Premium).

## Features

- Climate control for SQ610 and related thermostats
- MQTT shadow push with REST poll fallback
- Room temperature and heating setpoint as measurement sensors
- Heat-demand binary sensor from `RunningState`
- Switches, binary sensors, and OneTouch buttons when present on the account

## Install with HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. Repository: `https://github.com/rolki-png/ha-salus-it600-cloud`
3. Category: Integration
4. Download **Salus iT600 Cloud**, then restart Home Assistant
5. Settings → Devices & services → Add Integration → Salus iT600 Cloud
6. Sign in with the same email and password as the Salus Smart Home app

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rolki-png&repository=ha-salus-it600-cloud&category=integration)

## Manual install

Copy `custom_components/salus_it600_cloud` into your Home Assistant `config/custom_components/` directory and restart.

## Requirements

- Home Assistant 2024.1 or newer
- Salus Smart Home (EU) cloud account
- Network access to Cognito, Salus service API, and AWS IoT

## Support

Open an issue at https://github.com/rolki-png/ha-salus-it600-cloud/issues

## License

MIT. See [LICENSE](LICENSE).
