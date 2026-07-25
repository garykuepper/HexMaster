# Technical Reference

This document provides a deeper look into the architecture and implementation of HexMaster.

## Architecture

HexMaster is built with a modular approach to handle Discord interactions, database persistence, and external API sync.

- **Discord Bot**: Built with `discord.py` for handling slash commands and interactions.
- **Database**: PostgreSQL with `SQLAlchemy` and `asyncpg` for asynchronous database operations.
- **Sync Logic**: Standalone Python scripts for seeding regions and syncing with the Foxhole WarAPI.
- **OCR Integration**: Communicates with the [Foxhole Stockpiles](https://github.com/xurxogr/foxhole-stockpiles) (FS) service for image processing.

## Coding Standards

The Hexmaster codebase follows strict quality standards to ensure maintainability:

- **Strict PEP 8**: 4-space indentation, snake_case for functions/files, and CamelCase for classes.
- **50-Line Limit**: No public or private function exceeds 50 lines of code. Complex logic is modularized into helper methods.
- **100% Type Hinting**: Every function includes complete type hints for arguments and return values.
- **Documentation**: Google-style docstrings for all classes and methods.

## Project Structure

- **Bot Implementation**: [src/hexmaster/bot/main.py](file:///c:/Users/gkuep/PycharmProjects/Hexmaster/src/hexmaster/bot/main.py)
- **Database Schema**: [src/hexmaster/db/models.py](file:///c:/Users/gkuep/PycharmProjects/Hexmaster/src/hexmaster/db/models.py) (SQLAlchemy models)
- **Reference Data**: [data/](file:///c:/Users/gkuep/PycharmProjects/Hexmaster/data/) (Contains Towns, Regions, and the Item Catalog)
- **Scripts**: [scripts/](file:///c:/Users/gkuep/PycharmProjects/Hexmaster/scripts/) (Utilities for data syncing and seeding)

## Snapshot Model

HexMaster uses a **snapshot-based storage** model. Every stockpile report creates a new time-stamped record. This ensures that historical data is preserved and allows for trend analysis without losing previous state.

## Coordinate System

The bot uses a **Cartesian-Staggered** coordinate system to map Foxhole's hex-based world into a 2D plane. This allows for accurate distance calculations (in hex units) between towns across different regions.
