# FreshMart Intelligence AI 🛒🎙️

**FreshMart Intelligence AI** is a state-of-the-art, voice-native smart grocery shopping assistant. It enables users to build, manage, and confirm their shopping lists completely hands-free using real-time conversational AI. 

Built on top of **LiveKit** for ultra-low latency voice streaming, **Sarvam AI** for seamless Speech-to-Text (STT) and Text-to-Speech (TTS) optimized for Indian accents, and **Groq (Llama 3)** for lightning-fast natural language understanding.

---

## ✨ Features

- **🗣️ Real-time Voice Interaction:** Talk to "Priya", your shopping assistant, just like a real person. She listens, understands mid-sentence corrections, and updates your cart instantly.
- **⚡ Ultra-Low Latency:** Powered by LiveKit WebRTC and Groq's high-speed inference for conversational response times under 1 second.
- **🛒 Smart Entity Extraction:** The LLM automatically extracts items, categorizes them (Dairy, Vegetables, Spices, etc.), and intelligently infers standard units and quantities (e.g., converting "pav" to packets, or understanding default weights for apples vs. saffron).
- **🖼️ Dynamic Product Imagery:** Automatically fetches real-world product images via **Open Food Facts** to beautifully render your cart UI.
- **🔐 Secure Google Authentication:** One-click Google Sign-in to persist your shopping history and user profile across sessions.
- **📡 Live Data Sync:** The frontend UI stays perfectly synced with the backend state via Server-Sent Events (SSE).

---

## 🛠️ Technology Stack (in priority order)

### Core AI & Realtime Layer
- **Groq (Llama-3.3-70b-versatile)**  
  - Primary LLM that understands user intent, infers entities (items, categories, quantities), and decides how the cart should change.  
  - All higher-level behavior (adding/removing items, resolving ambiguities, handling corrections) ultimately flows from this model’s responses.
- **Sarvam AI (STT & TTS)**  
  - Converts user speech to text (STT) and the agent’s replies back to natural-sounding speech (TTS), optimized for Indian English/Hindi.  
  - If Sarvam is misconfigured, the entire voice loop breaks even if the LLM and backend are healthy.
- **LiveKit (Client & Python SDKs)**  
  - Real-time audio transport layer. Handles capturing microphone audio in the browser, sending it to the backend, and streaming synthesized speech back with ultra-low latency.  
  - Without LiveKit, the project degrades from a live voice assistant to a simple text chatbot.

### Application Backend
- **Python 3.10+ with FastAPI**  
  - Main HTTP API framework for authentication, UI routing, and Server-Sent Events (SSE) to keep the frontend synchronized with the conversation and cart state.  
  - Orchestrates calls to LiveKit, Groq, Sarvam AI, and MongoDB.
- **MongoDB**  
  - Persistent store for user profiles, historical shopping lists, and session data that must survive restarts.  
  - Enables personalization and history-aware behaviors (e.g., suggesting frequently bought items).

### Frontend & Client Experience
- **Vanilla HTML, CSS, JavaScript (ES6 Modules)**  
  - Lightweight, framework-free frontend that focuses on a polished UI and tight integration with the voice backend.  
  - Handles Google Sign-in, microphone access, LiveKit room connection, and rendering of the live cart.
- **Open Food Facts API (via frontend/backend calls)**  
  - Provides real-world product images and metadata so cart items feel like real grocery products instead of plain text entries.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- MongoDB instance (local or Atlas)
- API Keys for LiveKit, Groq, and Sarvam AI
- Google OAuth Client ID

### 1. Environment Setup

Create a `.env` file in the `customer-care-agent` directory with the following variables:

```env
# LiveKit Configuration
LIVEKIT_URL=wss://<your-project>.livekit.cloud
LIVEKIT_API_KEY=<your-api-key>
LIVEKIT_API_SECRET=<your-api-secret>
LIVEKIT_ROOM=shopping-room

# AI APIs
GROQ_API_KEY=<your-groq-key>
SARVAM_API_KEY=<your-sarvam-key>

# Database
MONGO_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority
DB_NAME=shopping_db

# Authentication
GOOGLE_CLIENT_ID=<your-google-client-id>
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Application

This architecture requires running two separate processes simultaneously: the HTTP API server and the Voice Worker.

**Terminal 1 (The Web Server):**
Serves the UI, handles Authentication, and streams UI updates.
```bash
python -m uvicorn backend.server:app --reload
```

**Terminal 2 (The Voice Worker):**
Connects to LiveKit, listens to user audio, processes LLM responses, and speaks back.
```bash
python -m backend.livekit_worker
```

### 4. Access the UI
Open your browser and navigate to:
`http://localhost:8000/ui`

---

## 🧪 Evaluation & Testing

FreshMart includes an automated evaluation suite to benchmark the LLM's accuracy across complex conversational scenarios (additions, deletions, hallucinations, quantity adjustments).

To run the test suite:
```bash
python -m backend.evaluate
```
This will test the agent against adversarial edge cases and output detailed Precision, Recall, and F1-Scores.

---

## 📂 Project Structure & File Responsibilities

Below is the high-level structure, followed by a detailed explanation of what each important file does.

```
customer-care-agent/
├── backend/
│   ├── server.py
│   ├── livekit_worker.py
│   ├── llm_agent.py
│   ├── db.py
│   ├── sarvam.py
│   ├── evaluate.py
│   └── transcript_store.py
├── frontend/
│   └── index.html
├── .env
└── requirements.txt
```

### Top-level files
- **`requirements.txt`**  
  - Lists all Python dependencies (FastAPI, LiveKit SDK, MongoDB client, Groq, Sarvam, etc.).  
  - This is the file you use with `pip install -r requirements.txt` to replicate the backend environment.

- **`.env`** (not checked into version control)  
  - Holds all sensitive configuration: API keys, database URIs, and OAuth client IDs.  
  - Loaded at runtime by the backend so secrets never need to be hard-coded in the codebase.

### `backend/` directory
- **`backend/server.py`** – **HTTP API & UI orchestration**
  - Defines the main FastAPI application instance (`app`).  
  - Exposes REST/SSE endpoints for:  
    - Serving the UI page and static assets.  
    - Handling Google authentication callbacks and validating ID tokens.  
    - Streaming live conversation and cart updates to the browser via SSE.  
  - Acts as the “brainstem” connecting frontend events (login, connect, refresh) with the long-running voice worker and database layer.

- **`backend/livekit_worker.py`** – **Realtime voice pipeline**
  - Connects to the configured LiveKit room using the LiveKit Python SDK.  
  - Listens to audio tracks from the user, applies Voice Activity Detection (VAD), and batches audio into segments suitable for STT.  
  - Sends audio chunks to Sarvam STT, forwards transcribed text to `llm_agent.py`, and receives structured actions (e.g., “add 2 kg potatoes”).  
  - Triggers Sarvam TTS to synthesize responses and publishes them back into the LiveKit room so the user hears “Priya” speaking.  
  - Coordinates with `transcript_store.py` to keep a consistent view of the conversation.

- **`backend/llm_agent.py`** – **LLM logic & entity extraction**
  - Wraps calls to Groq’s Llama model with carefully designed prompts.  
  - Takes raw user utterances (plain text) and returns a **structured JSON representation** describing:  
    - Operation type (add / remove / modify item).  
    - Item details (name, category, inferred quantity and units).  
    - Any clarifications or corrections needed.  
  - Deals with ambiguous language and mid-sentence corrections (e.g., “2 pav bread… actually make that 3, and brown bread, not white”).  
  - Enforces output schema validation so downstream code (DB and UI) can trust the shape of the data.

- **`backend/db.py`** – **Database access layer**
  - Creates and manages a MongoDB client connection using `MONGO_URI` and `DB_NAME` from `.env`.  
  - Defines helper functions to:  
    - Upsert user profiles based on Google identity.  
    - Store and fetch shopping lists and past sessions.  
    - Log structural events (items added/removed/updated) for evaluation or analytics.  
  - Centralizes all DB access so business logic never talks to MongoDB directly.

- **`backend/sarvam.py`** – **STT/TTS integration layer**
  - Provides thin wrapper functions around Sarvam’s Speech-to-Text and Text-to-Speech APIs.  
  - Handles:  
    - Authentication headers using `SARVAM_API_KEY`.  
    - Audio encoding/decoding formats expected by the API.  
    - Mapping between internal audio buffers and network payloads.  
  - Ensures other modules (like `livekit_worker.py`) can call simple Python functions instead of dealing with raw HTTP requests.

- **`backend/transcript_store.py`** – **In-memory conversation state**
  - Maintains an in-memory log of the ongoing conversation and cart state per user/session.  
  - Exposes methods for appending new user/assistant messages and querying current state.  
  - The SSE endpoints in `server.py` read from this store to push incremental updates to the frontend without hitting the database on every turn.

- **`backend/evaluate.py`** – **LLM evaluation harness**
  - Contains an automated suite for stress-testing the LLM agent with pre-defined conversational scenarios.  
  - Simulates complex dialogues (adds, deletes, quantity adjustments, contradictory instructions) and compares the LLM’s structured outputs against expected ground truth.  
  - Computes **Precision**, **Recall**, and **F1-score** to quantify how reliably the model manipulates the shopping list.  
  - Executed via:
    ```bash
    python -m backend.evaluate
    ```

### `frontend/` directory
- **`frontend/index.html`** – **UI, layout, and client logic**
  - Hosts the complete browser experience for FreshMart Intelligence AI.  
  - Responsibilities include:  
    - Rendering the main “glassmorphism” shopping dashboard and cart UI.  
    - Embedding or importing JavaScript that:  
      - Initiates Google Sign-in and forwards the ID token to the backend.  
      - Connects to LiveKit using credentials/room specified by the backend.  
      - Starts/stops microphone capture and handles permission prompts.  
      - Opens an SSE connection to `/events` (or equivalent) to receive live cart and transcript updates.  
      - Fetches and displays product thumbnails from Open Food Facts for each item.  
  - Acts as the single-page entrypoint; no heavy frontend frameworks are required.

---

## 🤝 Contributing
1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

*Happy Shopping! 🛒✨*
