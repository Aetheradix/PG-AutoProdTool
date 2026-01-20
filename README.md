# Auto Production Planning Tool (APPT)

This tool automates production planning based on Master Data inputs. It includes a CLI script for processing and a FastAPI backend.

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

## Installation

1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone <repository-url>
    cd PG-AutoProdTool
    ```

2.  **Create a Virtual Environment** (Recommended):
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # Linux/Mac
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**:
    Navigate to the `APPT` directory and install the required packages.
    ```bash
    cd APPT
    pip install -r requirements.txt
    ```

## Configuration

Before running the tool, ensure the Master Data Excel file is placed in the correct directory.

*   **File Name**: `Master Data - Auto Production Planning.xlsm`
*   **Location**: `APPT/data/input/`

If the folder structure does not exist yet, the script will create the folders, but you must manually add the Excel file.

## Usage

### 1. Running the CLI Tool
To run the main processing script, execute the following command from the `APPT` directory:

```bash
python src/main.py
```

This will:
- Load the Master Data.
- Validate the input files.
- Generate a draft plan in `APPT/data/output/`.

### 2. Running the API Server
To start the FastAPI backend server:

```bash
# Make sure you are in the APPT directory
uvicorn src.api.app:app --reload
```

The API will be available at: `http://127.0.0.1:8000`
API Documentation (Swagger UI): `http://127.0.0.1:8000/docs`

## Project Structure

```
PG-AutoProdTool/
├── APPT/
│   ├── data/
│   │   ├── input/      # Place input Excel files here
│   │   └── output/     # Generated results appear here
│   ├── src/
│   │   ├── api/        # FastAPI application
│   │   ├── main.py     # CLI entry point
│   │   └── config.py   # Configuration settings
│   └── requirements.txt
├── .gitignore
└── README.md
```
