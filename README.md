# AEL ERP - Project Blueprint & Structure

This document outlines the proposed structure for the AEL ERP application, designed to manage the trading and manufacturing operations of your steel business.

## 📋 Table of Contents

- [Core Modules](#1-core-modules)
- [Automation Workflows](#2-automation-workflows-future-implementation-plan)
- [Reports & Analytics](#3-reports--analytics)
- [Database Structure](#4-proposed-databasedata-structure-simplified)

---

## 1. Core Modules

The ERP will be organized into the following core modules, accessible from the main dashboard after login.

### 🔄 Trading Operations

This module will handle all activities related to buying and selling raw materials.

#### Data Entry Forms

- **Purchase Order (PO) to Mill**
  - Form to create a new PO for bulk raw material purchases from suppliers like JSW, SAIL
  - **Fields:** Supplier, Material Type, Grade, Quantity (in Tons), Rate, Expected Delivery Date, Transporter Details

- **Sales Order (SO) to Customer**
  - Form for when Amba sells raw materials to other traders/manufacturers
  - **Fields:** Customer, Material Details, Quantity, Sale Price, Payment Terms, Delivery Address

- **Kapson Trading Workflow Form**
  - A dedicated form for the Kapson Industries cycle
  - **Stage 1:** PO to Mill (for Kapson) - Similar to the standard PO form but flagged for the Kapson workflow
  - **Stage 2:** Log Kapson Motor Purchase - Form to record the purchase of finished motors from Kapson
    - **Fields:** Kapson PO Ref, Motor Specs, Quantity, Purchase Price from Kapson
  - **Stage 3:** Log Motor Sale to End Consumer - Form to record the final sale to customers like Siemens
    - **Fields:** End Customer (e.g., Siemens), Motor Details, Quantity, Final Sale Price

### 🏭 Manufacturing Operations

This module will manage the production of electrical stampings.

#### Data Entry Forms

- **Raw Material Allocation**
  - Form to allocate raw materials from inventory to a new manufacturing job
  - **Fields:** Job ID, Material Type, Quantity Allocated

- **Production Log**
  - Simple form to log daily production output
  - **Fields:** Job ID, Product (e.g., Electrical Stampings), Quantity Produced, Quality Check Status

- **Finished Goods Entry**
  - Form to add manufactured goods to the inventory
  - **Fields:** Job ID, Product Name, Quantity, Ready-for-Sale Status

### 📦 Inventory Management

A centralized module to track all stock.

#### Data Entry Forms

- **Add/Edit Stock Item**
  - Form to manually add or adjust stock levels
  - **Fields:** Item ID, Item Name, Category (Raw Material/Finished Good), Quantity, Unit, Warehouse Location

#### Views

- Real-time dashboard of raw materials and finished goods
- Stock aging report
- Low-stock alerts

### 💰 Accounting & Finance

To manage financial transactions.

#### Data Entry Forms

- **Log Expense**
  - A form to enter general business expenses
  - **Fields:** Category (Logistics, Salary, Utilities), Amount, Date, Vendor, Attached Invoice (upload)

- **Record Payment**
  - Log incoming/outgoing payments against invoices
  - **Fields:** Invoice ID, Amount Paid, Payment Date, Mode of Payment

---

## 2. Automation Workflows (Future Implementation Plan)

This section will house workflows that automate manual data entry.

### 📄 Invoice OCR Uploader

- **Functionality:** User uploads a Purchase Invoice (PDF/Image). The system uses Optical Character Recognition (OCR) to extract key details (Invoice #, Supplier, Items, Quantity, Rate, Total Amount, GST).
- **Action:** The extracted data pre-fills a verification form. Upon user confirmation, it automatically updates the inventory and creates a payable entry in the accounting module.

### 📊 Excel Order Uploader

- **Functionality:** User uploads a standardized Excel template for bulk sales orders.
- **Action:** The system parses the Excel file and creates multiple draft sales orders for user review and confirmation.

---

## 3. Reports & Analytics

This section will provide insights into business operations.

- **Sales Report:** Generate reports based on date range, customer, or product
- **Purchase Report:** Analyze raw material procurement costs and trends
- **Inventory Status Report:** A comprehensive view of all stock levels and values
- **Profit & Loss (P&L) Report (Simplified):** A high-level view of profitability per trading deal or manufacturing job

---

## 4. Proposed Database/Data Structure (Simplified)

We can start with simple CSVs or a SQLite database and later migrate to a more robust database.

| File | Description |
|------|-------------|
| `users.csv` | `(username, password_hash)` |
| `inventory.csv` | `(item_id, item_name, category, quantity, unit, location)` |
| `purchase_orders.csv` | `(po_id, supplier, material, quantity, rate, order_date, status)` |
| `sales_orders.csv` | `(so_id, customer, material, quantity, rate, order_date, status, invoice_id)` |
| `invoices.csv` | `(invoice_id, order_id, type, amount, status, due_date)` |
| `expenses.csv` | `(expense_id, category, amount, date, vendor)` |

---

This structure provides a clear and scalable foundation for building the AEL ERP application.