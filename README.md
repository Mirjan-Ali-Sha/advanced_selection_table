# Advanced Selection Table for QGIS

**A professional-grade attribute table plugin with two-tier selection for advanced feature filtering and editing.**

Advanced Selection Table enhances your QGIS workflow by providing a powerful two-tier selection system. It allows you to maintain your original layer selection (Cyan) while creating a temporary subset (Yellow) for targeted operations, editing, and analysis.

<img src="raw.githubusercontent.com/Mirjan-Ali-Sha/advanced_selection_table/blob/main/icons/icon.png" width="15" alt="Screenshot">
<!-- ![Screenshot](https://github.com/Mirjan-Ali-Sha/advanced_selection_table/blob/main/icons/icon.png){:width="15px"} -->

## Key Features

- **Two-Tier Selection System**:
  - **Cyan Background**: Shows your original layer selection (the "pool" of features).
  - **Yellow Highlighting**: Marks the specific subset you want to work with ("target" features).

- **Professional Selection Behavior**:
  - **Single Click**: Highlights a row (replaces previous highlights).
  - **Ctrl + Click**: Toggles individual rows in/out of the highlighted set.
  - **Shift + Click**: Selects a range of rows.
  - **"Highlight All" / "Clear Highlights"**: Quickly manage your working set.

- **Advanced Field Calculator**:
  - Target **only highlighted features** for updates (or all selected features if none highlighted).
  - Condition-based updates without writing complex SQL.
  - Expandable function tree with categories (String, Math, Date, Geometry).
  - Live preview of expression results.

- **Expression-Based Filtering**:
  - Filter your selection using a powerful expression builder.
  - **"Select by Expression"**: Highlights features that match your criteria within the existing selection.

- **Inline Editing**:
  - Double-click any cell to edit its value directly (requires layer Edit Mode).
  - Changes are committed immediately to the edit buffer.

- **Edit-Aware Tools**:
  - **Delete, Cut, Copy, Paste**: Operations automatically target the **highlighted (yellow)** features first.
  - If no features are highlighted, operations fall back to the full selection.
  - Tools are disabled if the layer is not in Edit Mode (preventing accidental clicks).

- **Dockable Interface**:
  - Use as a floating window or dock it to the bottom of your QGIS interface, just like the native attribute table.

## Installation

1. Open QGIS.
2. Go to **Plugins -> Manage and Install Plugins...**.
3. Search for "Advanced Selection Table".
4. Click **Install Plugin**.

## How to Use

### 1. Basic Workflow
1. **Select features** in your vector layer using any standard QGIS selection tool (Rectangle, Polygon, etc.).
2. Open **Advanced Selection Table** from the **Vector** menu or the **MAS Vector Processing** toolbar.
3. Your selected features appear in the table with a **Cyan** background.
4. **Click** rows to highlight them in **Yellow**. These are now your "active" features.
5. Perform operations (Calculator, Delete, Zoom) - they will apply to the **Yellow** features.

### 2. Selection Shortcuts
- **Click**: Highlight row (clears other highlights).
- **Ctrl + Click**: Add/Remove row from highlights.
- **Shift + Click**: Highlight distinct range of rows.
- **Spacebar**: Toggle highlight on current row.

### 3. Field Calculator
1. Click the **Field Calculator** icon in the toolbar.
2. Check **"Only update highlighted features"** to limit changes to your yellow subset.
3. Choose to **Update existing field** or **Create new field**.
4. Build your expression using the list of functions.
5. Click **OK** to run.

## License

This plugin is released under the GNU General Public License v2.0 (GPLv2).

## Author & Support

**Author**: Mirjan Ali Sha  
**Email**: mastools.help@gmail.com  
**Bug Tracker**: [GitHub Issues](https://github.com/mastools/advanced-selection-table/issues)

---
*Developed for professional GIS workflows.*
