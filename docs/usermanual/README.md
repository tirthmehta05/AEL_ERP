# AEL ERP User Manual

Welcome to the user manual for the AEL ERP application. This guide will walk you through the various features and how to use them.

## Table of Contents
1.  [Home Dashboard](#1-home-dashboard)
2.  [Data Entry](#2-data-entry)
    -   [Raw Material Inward Issue](#raw-material-inward-issue)
    -   [Raw Material Used](#raw-material-used)
    -   [Sales Order](#sales-order)
    -   [Assign Coils](#assign-coils)
    -   [Weight Receipt](#weight-receipt)
3.  [Slitting Plan](#3-slitting-plan)
4.  [PDF Generator](#4-pdf-generator)
    -   [Coil Sticker](#coil-sticker)
    -   [Slitting Plan PDF](#slitting-plan-pdf)
    -   [Job Card](#job-card)
    -   [Delivery Challan](#delivery-challan)
5.  [Automation Workflows](#5-automation-workflows)
6.  [Forms](#6-forms)

---

### 1. Home Dashboard

The Home page provides a quick overview of your business metrics. It features:
-   **Metric Cards:** Key performance indicators (KPIs) like Overall Revenue, Total Insight, and Total Inward Records are displayed at the top for a quick glance.
-   **Sales Summary Chart:** A visual representation of your sales performance over time.

### 2. Data Entry

This section is for all your data entry needs. It is organized into several tabs for different types of data.

#### Raw Material Inward Issue

This form is used to record new raw materials (coils) that you receive.

-   **Coil Entry:**
    -   Fill in the details of the coil, such as RM Receipt Date, Type, Grade, Thickness, etc.
    -   A unique **Coil Number** can be automatically generated based on the coil's properties, or you can enter it manually by checking the "Enter Coil Number Manually" box.
    -   You can add multiple coils to a list before submitting them all at once.
-   **Validate against Slitting Plan:**
    -   Optionally, you can validate the list of coils against one or more existing Slitting Plans to ensure the material matches the plan.
-   **Bulk Upload from Excel:**
    -   For entering a large number of coils at once, you can use the Excel upload feature. Download the template, fill it in, and upload it.

#### Raw Material Used

Use this form to record the consumption of raw materials.

-   Select the **Job Card** and the **Coil Number** that was used.
-   Enter the **Weight** of the material that was consumed.
-   The form will show you the available weight for the selected coil to prevent over-consumption.

#### Sales Order

This is where you create new sales orders for your customers.

-   **Order Details:** Fill in the main details of the order, such as Party Name, Order Date, PO Number, etc.
-   **Design Details:** Add one or more design details for the order, including dimensions and number of sets. The weight and stack are calculated automatically.
-   **Coil Assignment (Optional):** You can assign raw material coils to the order right away, or you can leave it for later.

#### Assign Coils

This tab is for assigning coils to sales orders that were created without an initial coil assignment.

-   Select a pending Sales Order from the dropdown.
-   The design details and required weight will be displayed.
-   Use the coil assignment UI to select and assign the necessary coils.

#### Weight Receipt

After production, use this form to record the actual weight of the produced items.

-   Select a **Party Name** and **date range** to find the relevant Job Card.
-   Select the **Job Card** from the dropdown.
-   The design details for that job card will be displayed in a table.
-   Enter the **Actual Weight** and an optional **Remark** for each design item in the table.
-   Click "Save Weight Receipt" to create a permanent record.

### 3. Slitting Plan

This page helps you create a plan for slitting wide coils into narrower ones.

-   **Filters:** Use the filters at the top to find the available raw material coils you want to use.
-   **Coil Selection:** Select one or more coils from the filtered list.
-   **Enter Slitting Sizes:** In the table, enter the desired **Slit Size (mm)** and the **Number of Slits** for each size.
-   **Calculated Plan & Summary:** The application will automatically calculate the weight for each slit, the total material used, and the amount of scrap.
-   **Save Plan:** Once you are satisfied with the plan, click "Save Slitting Plan" to save it. A unique Slitting Plan ID will be generated.

### 4. PDF Generator

This section allows you to generate various PDF documents.

#### Coil Sticker

-   Generate stickers for your raw material coils. Each sticker includes the coil number, weight, grade, and a QR code for easy scanning.

#### Slitting Plan PDF

-   Select a saved Slitting Plan to generate a printable PDF document that details the plan.

#### Job Card

-   Generate a Job Card PDF for a specific sales order. The PDF includes all the design details and the assigned coils.

#### Delivery Challan

-   Generate a Delivery Challan based on one or more Weight Receipts. This PDF is formatted as a professional receipt for your customers.

### 5. Automation Workflows

This section contains tools to automate your workflows.

-   **Invoice Processor (OCR):** Upload a purchase invoice, and the system will use Optical Character Recognition (OCR) to automatically extract the data.

### 6. Forms

This page provides quick links to various Microsoft Forms for data collection.
