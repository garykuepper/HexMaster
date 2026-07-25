# Admin Guide: HexMaster Configuration

Administrator permissions are required to run these commands. The bot uses these settings to determine faction tracking, API endpoints, and logistics targets.

## Setup Commands

### `/setup config`
Defines the server's faction and shard.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `faction` | Choice | No | Current | `Colonial` or `Warden`. |
| `shard` | Choice | No | `Alpha` | `Alpha`, `Bravo`, or `Charlie`. |

### `/setup priorities`
Initializes target quantities from templates.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `template` | Choice | **Yes** | - | `Standard Logistics` or `Clear All`. |

> [!TIP]
> Logistics hubs like Seaports and Storage Depots are automatically calculated with a **4x multiplier** of these target values during requisitions to maintain strategic depth.

### `/setup cleanup_commands`
Removes old guild-specific commands to resolve duplicates. No parameters.

---

## Priority Management

### `/priority add`
Adds or updates a target for a specific item.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `item` | String | **Yes** | - | Item name from the catalog. |
| `min_crates` | Integer | **Yes** | - | The target amount in **crates**. |
| `priority` | Float | **Yes** | - | Priority weight (Lower numbers rank higher). |

### `/priority list`
Displays the current priority list for the server. No parameters.

### `/priority remove`
Removes an item's target settings.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `item` | String | **Yes** | - | Item name (Autocomplete supported). |

---

## System Diagnostics

- `/system_status`: Comprehensive overview of DB/WarAPI status and latency.
- `/snapshots [limit]`: View recent report history. `limit` defaults to 10.
- `/ping`: Simple database and bot latency test.
- `/db_stats`: Raw counts of snapshots and items in storage.
- `/check_towns` / `/check_regions` / `/check_priority`: Quick validation of seeded reference data.
