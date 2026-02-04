# Hexmaster — Foxhole Logistics Discord Bot

Hexmaster is a powerful Discord bot designed for **Foxhole** logistics groups. It enables seamless stockpile management, cross-map item discovery, and intelligent supply chain comparison using OCR and real-time game data.

The bot follows a **snapshot-based storage** model, preserving full historical data of every stockpile update without ever overwriting.

---

## What Hexmaster Does (MVP)

### 1. Stockpile Ingestion (OCR)

- **Automatic Scanning**: Users upload screenshots of stockpiles via a slash command.
- **Deep Processing**: The bot uses an OCR service to transcribe item codes, names, total quantities, and crate statuses.
- **Historical snapshots**: Every import creates a new time-stamped record for trend analysis.

### 2. Intelligent Comparison (`/compare`)

- **Supply Chain Decisioning**: Compare a "Shipping Hub" (e.g., Seaport/Warehouse) against a "Receiving Town/Base".
- **Hub Detection**: Automatically detects Seaports and Storage Warehouses to apply a **4x requirement multiplier**.
- **Crate-First Units**: All quantities are standardized to "Crates" for easy logistics math.
- **Priority Logic**: Sorts items by mission-critical importance and highlights shortages.

### 3. Cross-Map Discovery (`/find`)

- **Global Search**: Find which stockpiles currently hold a specific item across the entire World Conquest map.
- **Accurate Hex Math**: Uses a custom **Cartesian-Staggered** coordinate system to calculate distances in physical hex units.
- **Proximity Sorting**: Results are sorted by distance from your reference town.
- **Sync with WarAPI**: Automatically fetches 918+ town locations and marker types (Major/Minor) from the official Foxhole servers.

---

## Architecture

- **Discord Bot**: Built with `discord.py` and `SQLAlchemy`.
- **Database**: PostgreSQL with `asyncpg` for high-performance async queries.
- **Sync Logic**: Standalone Python scripts for seeding regions and syncing with WarAPI.
- **Dockerized**: Fully containerized for easy deployment on Linux/Windows.

---

## Future Roadmap & UI Updates

While the core logic is now stable, the following UI and feature enhancements are planned:

### **Live War Intelligence (WarAPI integration)**

- **Dynamic Inventory Cleanup**: Automatically remove or "grey out" inventories for Seaports or Storage Warehouses that the WarAPI reports as **Destroyed** or **Captured** by the enemy.
- **Faction Tracking**: Only show inventories that belong to the bot-owner's faction (Colonials/Wardens) in real-time.
- **Logistics Threat Mapping**: Overlay current "Front Line" map data to warn logistics drivers if a `/find` result requires driving through contested or enemy-held territory.
- **Supply Drop Alerts**: Automated pings when a critical frontline base (based on WarAPI status) is low on Soldier Supplies or AT weapons.

### **Interactive Visualization & Web UI**

- **Stockpiles at a Glance**: A browser-based dashboard to view all current inventories without checking Discord.
- **Shortage Heatmap**: Visual representation of which regions are currently under-supplied.
- **Trend Charts**: Visual graphs of stockpile changes over the last 24-48 hours.

### **Advanced Logistics Tools**

- **Optimal Route Finder**: Suggest the fastest/safest path between a Shipping Hub and a frontline base, accounting for current road connectivity and bridge status.
- **Delivery Tracker**: Tooling for users to mark "Incoming" supplies to prevent over-shipping to a single base.

---

## Getting Started

### 1) Prerequisites

- Docker & Docker Compose
- Discord Bot Token
- [FIR](https://github.com/GICodeWarrior/fir) (cloned in the same parent directory)

### 2) Environment Setup

1. Create a `.env` file from `.env.example`:

   ```env
   DISCORD_TOKEN=your_token_here
   DATABASE_URL=postgresql+asyncpg://hexmaster:hexmaster@postgres:5432/hexmaster
   OCR_URL=http://fir-ocr:5000
   ```

2. Ensure the `fir` repository is cloned alongside `Hexmaster`:

   ```bash
   cd ..
   git clone https://github.com/GICodeWarrior/fir.git
   ```

### 3) Launch

Start the entire stack (Bot + Database + OCR Service):

```bash
docker compose up --build -d
```

---

## Development & Seeding

To update town data or region offsets manually:

```bash
python -m scripts.seed_and_sync
```

This is handled automatically during setup.

---

## Credits & Attribution

Hexmaster relies on several critical community-maintained tools and APIs:

- **FIR (Foxhole Inventory Reporter)**: All OCR and screenshot-to-data logic is powered by [FIR](https://github.com/GICodeWarrior/fir). This project uses the fir-ocr methodology for its ingestion pipeline.
- **Foxhole WarAPI**: Live town data, map status, and hex regions are provided by the official [WarAPI](https://github.com/clapfoot/warapi) maintained by Clapfoot/Siege Camp.
- **Discord.py**: High-level Discord API wrapper.
- **SQLAlchemy & asyncpg**: Database abstraction and performance.

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for the full text.

Hexmaster's implementation is intended for private logistics group use and follows all community safety standards for Foxhole third-party software.
