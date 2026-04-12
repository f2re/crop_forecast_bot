# Crop Forecast Bot - Context for Gemini CLI

## Project Overview
An intelligent Telegram bot for farmers and agronomists providing crop recommendations based on climate (ERA5/Open-Meteo), soil (SoilGrids), and satellite (GEE) data.

## Core Stack
- **Language:** Python 3.11+
- **Bot Framework:** aiogram 3.x (Async)
- **RAG Engine:** ChromaDB + Sentence-Transformers (paraphrase-multilingual-MiniLM-L12-v2)
- **Data:** pandas, SQLAlchemy (PostgreSQL), openmeteo-requests
- **Scheduler:** APScheduler (for frost alerts and daily digests)
- **Infrastructure:** Docker (multi-stage), Docker Compose

## Key Modules
- `src/agro/`: Agronomic indices (GDD, HTC/ГТК, SPI, ET0/FAO-56).
- `src/knowledge/`: RAG implementation and LLM advisor logic.
- `src/bot/`: Telegram handlers, keyboards, and scheduling.
- `src/api/`: Data retrieval from climate and soil APIs.
- `src/database/`: SQLAlchemy models and CRUD operations.

## Architecture Guidelines
- **Strict Async:** No blocking calls in handlers or service layers.
- **Layer Separation:** Handlers -> Services -> API/DB.
- **RAG Integration:** All agronomic advice must be grounded in the literature base via `src/knowledge/rag_engine.py`.
- **Farmer-Centric UX:** Avoid technical jargon (NDVI, ERA5, API) in user-facing messages.

## Development Status
- Migrated from telebot to aiogram 3.x.
- RAG module fully implemented with support for multiple LLM providers (Groq, OpenAI).
- Automated scheduling for frost alerts is active.
