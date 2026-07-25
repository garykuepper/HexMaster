# User Guide: HexMaster Commands

HexMaster provides several logistics and reconnaissance commands to help your faction manage stockpiles effectively.

## Core Commands

### `/report`

Files an intelligence report by uploading a screenshot to the OCR service.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `image` | Attachment | **Yes** | - | The stockpile screenshot file. |
| `town` | String | **Yes** | - | The name of the town (Autocomplete supported). |
| `stockpile` | String | No | `Public` | The name of the stockpile. |

### `/inventory`

Displays the current items and quantities for a specific location.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `town` | String | **Yes** | - | The name of the town (Autocomplete supported). |
| `structure` | String | No | `All` | Filter by structure type (e.g., `Seaport`, `Depot`). |
| `stockpile` | String | No | `All` | Filter by a specific stockpile name. |

- **Report Age**: The output header explicitly lists the **age** of the latest report (e.g., `(2h ago)`), so you know how fresh the intelligence is.

### `/locate`

Searches globally for an item, sorted by distance from your reference town.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `item` | String | **Yes** | - | The item name (Autocomplete from tracked items). |
| `from_town` | String | **Yes** | - | Your current location for distance calculation. |

### `/requisition`

Calculates a logistics order between two towns based on server priorities.

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `ship_town` | String | **Yes** | - | The town supplying the goods (Autocomplete shows Hubs with reports). |
| `recv_town` | String | **Yes** | - | The destination town (Autocomplete shows towns with reports). |
| `ship_struct` | String | No | `All` | Specific shipping structure filter. |
| `ship_stockpile`| String | No | `All` | Specific shipping stockpile filter. |
| `recv_struct` | String | No | `All` | Specific receiving structure filter. |
| `recv_stockpile`| String | No | `All` | Specific receiving stockpile filter. |
| `multiplier` | Float | No | `Auto`* | Multiplier for targets. |

- **Automatic Multiplier**: For major logistics hubs (**Seaports** and **Storage Depots**), HexMaster automatically applies a **4x multiplier** to the target quantities from the priority list. Bases default to **1x**.
- **Report Tracking**: Shows the age of reports for both the shipping and receiving locations.

---

## Tips & Table Features

All tabular outputs are color-coded.

- **Autocompletes**: Most parameters like `town`, `item`, and `structure` provide autocompletes based on current reports. Town lookups in `/inventory` and `/requisition` only show locations that have already been reported to the system.
- **Color-Coded Tables**:
  - 🟢 **Green**: Stockpile meets or exceeds the target priority level.
  - 🔴 **Red**: Stockpile is below target and requires supply.
  - 🟡 **Yellow**: (Requisition only) Item is available at the shipping source but target is not yet met.
- **Pagination**: If an inventory or search list is longer than 20 rows, use the **Previous** and **Next** buttons to flip through pages.
- **Lore & Help**: Use `/help` for a quick command summary and system status overview.
