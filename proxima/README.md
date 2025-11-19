# Proxima Trading - Local Stock Web App (Flask + SQLite)

This local web app manages **Products**, **Clients**, **Invoices (Factures)**, **Payments**, **Returns**, and **Inventory**.
It enforces uniqueness for `REF_PRODUIT`, `N°FACUTRE`, and `N°PAYEMENT`. Finalizing an invoice accounts for sales; returns restore stock. Payments support **partial application** via a link table.

## Quick start

1. Install Python 3.11+ and pip.
2. Open a terminal in this folder and create a virtual environment:
   ```bash
   python -m venv .venv
   # Windows PowerShell
   .venv\Scripts\Activate.ps1
   # macOS/Linux
   source .venv/bin/activate
   ```
3. Install deps:
   ```bash
   pip install -r requirements.txt
   ```
4. Run:
   ```bash
   flask --app app run --debug
   ```
5. Open http://127.0.0.1:5000
