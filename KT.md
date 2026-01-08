# Advanced Selection Table - Knowledge Transfer (KT)

## 1. Overview
The **Advanced Selection Table** is a professional-grade QGIS plugin designed to provide an enhanced attribute table experience. Its core philosophy is a **Two-Tier Selection System**, allowing users to work with a "Selection within a Selection."

### Key Features
*   **Two-Tier Selection**:
    *   **Cyan (Original Selection)**: Features selected in the main QGIS map.
    *   **Yellow (Highlighted Subset)**: A subset of the cyan selection, used for targeted operations (delete, copy, calculate).
*   **Dockable Interface**: Fully integrated QGIS dock widget (like the native attribute table).
*   **Advanced Filtering**: Filter within selections using expressions.
*   **Targeted Editing**: Edit, Delete, or Calculate fields only on the highlighted subset.

---

## 2. Architecture & File Structure

The project has been modularized for maintainability.

```
advanced_selection_table/
├── advanced_selection_table.py    # Main Entry Point (Plugin Loader)
├── ui/                            # UI & Review Modules
│   ├── __init__.py
│   ├── selection_widget.py        # CORE LOGIC: The main table widget
│   ├── delegates.py               # CUSTOM PAINTING: Handles Cyan/Yellow colors
│   ├── filter_dialog.py           # ADVANCED FILTER: Expression builder logic
│   └── calculator_dialog.py       # CALCULATOR: Field calc logic
├── icons/                         # Icon resources
└── metadata.txt                   # QGIS Plugin Metadata
```

---

## 3. Deep Dive: Core Logic

### A. The Two-Tier Selection System
The logic is maintained in `ui/selection_widget.py -> AdvancedSelectionWidget`.
This system isolates user actions in the table from the global QGIS selection until specific operations are performed.

*   `self.original_selection`: A `set` of Feature IDs (FIDs) corresponding to the standard QGIS layer selection (Cyan).
*   `self.highlighted_features`: A `set` of FIDs corresponding to the user's secondary selection in our table (Yellow).
*   **Synchronization**:
    *   When QGIS selection changes (`layer.selectionChanged`), `original_selection` is updated and the table resets.
    *   When user clicks rows in table (`itemSelectionChanged`), `highlighted_features` is updated and the Yellow rubber band redraws.

### B. Custom Coloring (The Delegate)
We override standard Qt selection behaviors to prevent the default "Blue" highlight and enforce our Cyan/Yellow scheme.
*   **File**: `ui/delegates.py`
*   **Class**: `HighlightDelegate`
*   **Mechanism**:
    1.  Intercepts the `paint()` event.
    2.  Use `painter.fillRect()` to draw Cyan or Yellow backgrounds based on FID status.
    3.  **Critical**: Removes `QStyle.State_Selected` from the option state to disable default Qt highlighting.

```python
# Code Snippet from delegates.py
def paint(self, painter, option, index):
    # ...
    option.state = option.state & ~QStyle.State_Selected  # <--- CRITICALLY IMPORTANT
    
    painter.save()
    if fid in self.dialog.highlighted_features:
         painter.fillRect(option.rect, self.YELLOW_COLOR)
    elif fid is not None:
         painter.fillRect(option.rect, self.CYAN_COLOR)
    painter.restore()
    # ...
```

### C. Map Canvas Interaction (Rubber Bands)
To ensure the map reflects the table state, we use **Rubber Bands** (`QgsRubberBand`).
*   **Cyan Rubber Band**: Draws a transparent cyan overlay for all items in `original_selection`.
*   **Yellow Rubber Band**: Draws a bright yellow overlay for items in `highlighted_features`.
*   **Logic**:
    *   Created in `setup_rubber_bands`.
    *   Updated via `update_map_highlighting`.
    *   **Cleanup**: Crucial! `cleanup_rubber_bands()` MUST be called during plugin unload/dock close to prevent "ghost" shapes. This is explicitly handled in `AdvancedSelectionTable.unload()`.

### D. Sorting & FID Tracking
Since QGIS tables (and `QTableWidget`) visual row indices change when sorted, we cannot rely on row numbers to identify features.
*   **Solution**: We store the Feature ID (FID) directly in the table item's data using a generic Qt Role.
*   **Implementation**: `item.setData(Qt.UserRole + 1, fid)`
*   **Retrieval**: `get_fid_for_row(row)` reads this hidden data, ensuring operations trigger on the correct feature even after sorting.

### E. Advanced Filtering (`ui/filter_dialog.py`)
This dialog builds QGIS expressions to filter *within* the current selection.
*   **Value Caching**: On init, it iterates through *selected features only* to cache unique values for every field. This allows the "Values" list to be context-aware.
*   **Condition Builder**:
    *   Supports `AND`, `OR`, `NOT` logic.
    *   Can build complex clauses like `IN (...)` or `BETWEEN`.
    *   Stores conditions as a list of `(logic_operator, condition_string)` tuples.
*   **Testing**: `test_expression()` manually evaluates the current string against the selected features to give immediate feedback.

### F. Field Calculator (`ui/calculator_dialog.py`)
Replicates the native QGIS field calculator but scopes it to our specific subsets.
*   **Targeting**:
    *   If `highlighted_features` exist, defaults to updating *only* those (Yellow).
    *   Otherwise, updates all `original_selection` (Cyan).
*   **Modes**:
    *   **Create New Field**: Adds a new attribute column before calculating.
    *   **Update Existing**: Modifies values in place.
*   **Feature Navigation**: Includes "Preview" logic (`update_preview`) that lets you step through features to see how the expression evaluates on specific rows.

---

## 4. Workflows & Signals

### Initialization
1.  `AdvancedSelectionTable.initGui()` creates the toolbar buttons.
2.  Clicking "Dock" triggers `run_dock()`.
3.  `AdvancedSelectionWidget` is instantiated. Old rubber bands are cleared.

### Selection Change (QGIS -> Plugin)
1.  `QgsVectorLayer.selectionChanged` signal fires.
2.  Widget updates `self.original_selection`.
3.  Table repopulates.

### Selection Change (Plugin -> Map)
1.  User clicks a row (Standard Click / Ctrl+Click).
2.  `itemSelectionChanged` signal fires.
3.  Widget updates `self.highlighted_features`.
4.  `update_map_highlighting()` redraws the Yellow rubber band.

### Plugin Unload
1.  `unload()` called by QGIS.
2.  Iterates through all open docks.
3.  **Forces `cleanup_rubber_bands()`** on each widget.
4.  Removes dock widget.

---

## 5. Development Guidelines
*   **Edit Safe**: Always check `layer.isEditable()` before performing write operations.
*   **Transactions**: Use `layer.beginEditCommand()` and `endEditCommand()` (implicit in some wrapper methods) or check `layer.changeAttributeValue()` returns.
*   **Clean Up**: Always ensure rubber bands are removed in `closeEvent` or `unload`.
*   **Icons**: Store in `icons/` folder. Use `QIcon(os.path.join(self.plugin_dir, 'icons', 'icon_name.png'))`.
