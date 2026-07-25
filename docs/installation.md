# Installation & Deployment Guide

This guide covers how to get HexMaster up and running on your own server.

## Prerequisites

- **Docker & Docker Compose**: The recommended way to run HexMaster.
- **Discord Bot Token**: Create one at the [Discord Developer Portal](https://discord.com/developers/applications).
- **Foxhole Stockpiles (FS)**: A running instance of [Foxhole Stockpiles](https://github.com/xurxogr/foxhole-stockpiles) is required for OCR processing.

---

## Installation (Docker)

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/garykuepper/HexMaster.git
    cd HexMaster
    ```

2.  **Configure Environment**:
    Fill in your tokens in `.env`.
    ```bash
    DISCORD_TOKEN=your_token_here
    DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/hexmaster
    OCR_URL=http://fs-api:8000
    ```

3.  **Run with Docker Compose**:
    ```bash
    docker-compose up -d
    ```

---

## Development & Maintenance

### Manually Update Data
To sync regions or re-seed the item catalog:
```bash
python -m scripts.sync_regions
python -m scripts.seed_catalog
```

### Technical Standard
All contributions must follow the **Refactored Architecture**:
- Complete type hinting.
- Google-style docstrings.
- Maximum 50 lines per function.
- Adherence to PEP 8.
