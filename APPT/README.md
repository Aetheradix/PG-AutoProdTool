# Auto Production Planner Tool (APPT)

A Python-based tool for automating production planning tasks.

## 🚀 Features
- **Master Data Loading**: Ingests SKU and washout rule data from Excel.
- **Database Integration**: Connects to a MySQL database for retrieving raw material data.
- **Production Logic**: Applies production constraints and routing logic (Phase 1).
- **Automated Reporting**: Generates draft production plans in Excel format.

## 🛠️ Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd PG-AutoProdTool/APPT
    ```

2.  **Set up a virtual environment (Recommended):**
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

1.  **Environment Variables**:
    Copy the example environment file and configure it with your database credentials.
    ```bash
    copy .env.example .env
    ```
    
    Edit `.env` and fill in your details:
    ```ini
    DB_USER=root
    DB_PASSWORD=your_secure_password
    DB_HOST=localhost
    DB_PORT=3306
    DB_NAME=pg_auto_tool
    ```

2.  **Input Data**:
    Ensure the `Master Data - Auto Production Planning.xlsm` file is placed in `data/input/`.

## 🏃 Usage

Run the main application:

```bash
python src/main.py
```

The tool will:
1.  Connect to the configured database.
2.  Load master data from the input Excel file.
3.  Generate a draft production plan in `data/output/`.

## 📁 Project Structure

-   `src/`: Source code (logic, database connection, configuration).
-   `data/`: Input and output data directories.
-   `.env`: Local environment variables (do not commit).
-   `requirements.txt`: Python package dependencies.
