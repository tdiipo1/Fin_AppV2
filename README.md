# FinApp V2: Local-First Finance Manager

## 🏗 Architecture Overview

This application is a local-first, privacy-focused financial management tool. It replaces the previous Streamlit prototype with a robust database-backed architecture.

**Core Principles:**
*   **Local Data**: Your data lives in `finapp_v2.db` on your machine. It is never sent to the cloud (except for optional anonymized API calls you configure, like AI categorization).
*   **Offline Capable**: Works fully without an internet connection.
*   **Deduplication**: Uses SHA256 fingerprinting to prevent duplicate transactions even when importing overlapping CSVs.

## 🚀 Getting Started

This folder (`Fin_App_V2`) is a self-contained project. You can move it anywhere on your computer.

### 1. Installation

Requires Python 3.10+

```bash
# It is recommended to create a virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Running the App

```bash
python main.py
```

The application will start at `http://localhost:8081`.

## 🛡️ Security & Backups

*   **Daily Backups**: The system automatically backs up your database to the `backups/` folder every time you start the app (once per day). It retains the last 30 days of backups.
*   **Git Privacy**: The `.gitignore` file is configured to exclude your database (`finapp_v2.db`) and backup folder. You can safely initialize a git repository in this folder to track your code changes without exposing your financial data.

## 📂 Project Structure

*   `main.py`: Entry point.
*   `database/`: Database models and connection logic.
*   `services/`: Business logic (Importer, deduplication, AI).
*   `ui/`: The user interface (NiceGUI).
*   `finapp_v2.db`: Your local database (created on first run).
