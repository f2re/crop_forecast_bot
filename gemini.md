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

## Multi-Agent System Blueprint (Planned)
The project is migrating to a multi-agent architecture powered by Google Gemini (genai SDK v1.0+).

- **Orchestrator Agent (gemini-2.5-pro):** Coordinates sub-agents and aggregates results for Telegram.
- **Data Collection Agent (gemini-2.0-flash):** Fetches ERA5, SoilGrids, and Satellite data via tools.
- **RAG Advisor Agent (gemini-2.0-flash):** Provides agronomic advice using ChromaDB and scientific literature.
- **Forecast Agent (gemini-2.0-flash):** Wraps existing Random Forest models for crop recommendations.
- **Scheduler Agent (gemini-2.0-flash):** Manages frost alerts and daily report generation.
- **Vision Agent (gemini-2.0-flash):** Analyzes crop photos for disease/pest identification (multimodal).

## Key Modules
- `src/agents/`: (Planned) Multi-agent system implementations (orchestrator, data, rag, forecast, scheduler, vision).
- `src/agro/`: Agronomic indices (GDD, HTC/ГТК, SPI, ET0/FAO-56).
- `src/knowledge/`: RAG implementation and LLM advisor logic.
- `src/bot/`: Telegram handlers, keyboards, and scheduling.
- `src/api/`: Data retrieval from climate and soil APIs.
- `src/database/`: SQLAlchemy models and CRUD operations.

## Architecture Guidelines
- **Strict Async:** No blocking calls in handlers or service layers.
- **Layer Separation:** Handlers -> Services -> API/DB.
- **RAG Integration:** All agronomic advice must be grounded in the literature base via `src/knowledge/rag_engine.py`.
- **Agentic Workflow:** Prefer delegating specialized tasks to sub-agents rather than monolithic logic.
- **Farmer-Centric UX:** Avoid technical jargon (NDVI, ERA5, API) in user-facing messages.

## Development Status
- **Current:** aiogram 3.x bot with functional RAG and automated scheduling.
- **Next Steps:** Implementing Phase 1 & 2 of the Multi-Agent system (Base Agent, Data/Forecast/RAG/Vision Agents).
