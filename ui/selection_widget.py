# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolBar, QTableWidget, 
    QAbstractItemView, QHeaderView, QAction, QMessageBox, QDockWidget, 
    QDialog, QFrame, QPushButton, QSizePolicy, QComboBox, QTableWidgetItem,
    QMenu, QApplication
)
from qgis.core import QgsFeatureRequest, QgsFeature, QgsApplication
from qgis.gui import QgsRubberBand

from .delegates import HighlightDelegate
from .filter_dialog import SelectionFilterDialog
from .calculator_dialog import FieldCalculatorDialog

class AdvancedSelectionWidget(QWidget):
    """
    Professional attribute table widget with two-tier selection:
    - Cyan background: Original selected features
    - Yellow background: Highlighted subset for operations
    
    Click behaviors (same as standard table selection):
    - Single click: Replace highlights with clicked row only
    - Ctrl+Click: Toggle row in/out of highlighted set
    - Shift+Click: Range selection for highlighting
    """
    
    CYAN_COLOR = QColor(0, 255, 255)        # Original selection (cyan)
    YELLOW_COLOR = QColor(255, 255, 0)      # Highlighted subset (yellow)
    
    highlightChanged = pyqtSignal(set)
    closed = pyqtSignal()
    dockRequested = pyqtSignal()  # Signal to request docking

    def __init__(self, layer, iface, plugin_dir, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.iface = iface
        self.plugin_dir = plugin_dir
        
        # Two-tier selection system
        self.original_selection = set(layer.selectedFeatureIds())  # Cyan rows
        self.highlighted_features = set()  # Yellow rows (subset)
        
        # For clipboard operations
        self.clipboard_features = []
        
        # For shift-click range selection
        self.last_clicked_row = None
        
        # Prevent circular updates
        self._updating_selection = False
        self._updating_highlights = False  # Prevent highlight overwrite during programmatic changes
        
        # Row to feature ID mapping
        self.row_to_fid = {}
        self.fid_to_row = {}
        
        # Create rubber bands for map canvas highlighting
        self.setup_rubber_bands()
        
        self.setup_ui()
        self.populate_table()
        self.connect_signals()
        self.update_button_states()
        
        # Initial map highlight
        self.update_map_highlighting()
    
    def setup_rubber_bands(self):
        """Create rubber bands for map canvas feature highlighting"""
        canvas = self.iface.mapCanvas()
        
        # Determine geometry type for rubber band
        geom_type = self.layer.geometryType()
        
        # Cyan rubber band for original selection (background)
        self.cyan_rubber_band = QgsRubberBand(canvas, geom_type)
        self.cyan_rubber_band.setColor(QColor(0, 255, 255, 180))  # Cyan with transparency
        self.cyan_rubber_band.setFillColor(QColor(0, 255, 255, 100))
        self.cyan_rubber_band.setWidth(2)
        
        # Yellow rubber band for highlighted features (foreground)
        self.yellow_rubber_band = QgsRubberBand(canvas, geom_type)
        self.yellow_rubber_band.setColor(QColor(255, 255, 0, 255))  # Bright yellow
        self.yellow_rubber_band.setFillColor(QColor(255, 255, 0, 150))
        self.yellow_rubber_band.setWidth(3)

    def cleanup_rubber_bands(self):
        """Remove rubber bands from map canvas - MUST be called on close"""
        try:
            canvas = self.iface.mapCanvas()
            
            if hasattr(self, 'cyan_rubber_band') and self.cyan_rubber_band:
                self.cyan_rubber_band.reset()
                try:
                    canvas.scene().removeItem(self.cyan_rubber_band)
                except:
                    pass
                self.cyan_rubber_band = None
            
            if hasattr(self, 'yellow_rubber_band') and self.yellow_rubber_band:
                self.yellow_rubber_band.reset()
                try:
                    canvas.scene().removeItem(self.yellow_rubber_band)
                except:
                    pass
                self.yellow_rubber_band = None
            
            # Force canvas refresh to ensure visual update
            canvas.refresh()
        except Exception as e:
            # Log but don't crash
            pass

    def setup_ui(self):
        """Build the widget UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self.setLayout(layout)
        
        # Info label showing counts
        self.info_label = QLabel()
        self.info_label.setStyleSheet("font-size: 11px; padding: 3px; background-color: #f0f0f0; border-radius: 2px;")
        self.update_info_label()
        layout.addWidget(self.info_label)
        
        # Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(self.toolbar.iconSize() * 0.85)
        layout.addWidget(self.toolbar)
        
        # Create custom table widget with stylesheet to override selection colors
        self.table_widget = QTableWidget()
        self.table_widget.setAlternatingRowColors(False)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_widget.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_widget.verticalHeader().setDefaultSectionSize(22)
        self.table_widget.verticalHeader().setVisible(True)
        # Enable sorting
        self.table_widget.setSortingEnabled(True)
        
        # Context menu
        self.table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        # Install custom delegate to override Qt's selection highlighting
        self.delegate = HighlightDelegate(self, self.table_widget)
        self.table_widget.setItemDelegate(self.delegate)
        
        layout.addWidget(self.table_widget)
        
        # Create toolbar actions
        self.create_actions()
        
        # Help label
        help_label = QLabel(
            "<small><b>Click</b>: Select | <b>Ctrl+Click</b>: Add/Remove | "
            "<b>Shift+Click</b>: Range | <b>Double-Click</b>: Edit (when editing) | "
            "<b>Yellow</b> = Highlighted for operations</small>"
        )
        help_label.setStyleSheet("color: #666; padding: 2px; font-size: 10px;")
        layout.addWidget(help_label)

    def create_actions(self):
        """Create toolbar actions"""
        # Clear Highlights action
        self.action_clear_highlights = QAction(
            self.get_icon('icons/clear_highlight.png'), 
            'Clear Highlights', self
        )
        self.action_clear_highlights.setToolTip('Clear all yellow highlights')
        self.action_clear_highlights.triggered.connect(self.clear_highlights)
        self.toolbar.addAction(self.action_clear_highlights)
        
        # Highlight All action
        self.action_highlight_all = QAction(
            self.get_icon('icons/highlight_all.png'), 
            'Highlight All', self
        )
        self.action_highlight_all.setToolTip('Highlight all rows')
        self.action_highlight_all.triggered.connect(self.highlight_all)
        self.toolbar.addAction(self.action_highlight_all)
        
        # Re-select to Highlighted action (narrow selection to highlighted subset)
        self.action_reselect = QAction(
            self.get_icon('icons/reselect.png'), 
            'Re-select to Highlighted', self
        )
        self.action_reselect.setToolTip('Make highlighted features the new selection (narrow down)')
        self.action_reselect.triggered.connect(self.reselect_to_highlighted)
        self.toolbar.addAction(self.action_reselect)
        
        self.toolbar.addSeparator()
        self.action_select_expr = QAction(
            self.get_icon('icons/select_expression.png'), 
            'Select by Expression', self
        )
        self.action_select_expr.setToolTip('Filter by expression')
        self.action_select_expr.triggered.connect(self.select_by_expression)
        self.toolbar.addAction(self.action_select_expr)
        
        # Invert Selection
        self.action_invert = QAction(
            QgsApplication.getThemeIcon('/mActionInvertSelection.svg'), 
            'Invert Highlights', self
        )
        self.action_invert.setToolTip('Invert highlights')
        self.action_invert.triggered.connect(self.invert_highlights)
        self.toolbar.addAction(self.action_invert)
        
        self.toolbar.addSeparator()
        
        # Delete action
        self.action_delete = QAction(
            QgsApplication.getThemeIcon('/mActionDeleteSelectedFeatures.svg'), 
            'Delete', self
        )
        self.action_delete.setToolTip('Delete highlighted features')
        self.action_delete.triggered.connect(self.delete_features)
        self.toolbar.addAction(self.action_delete)
        
        # Cut action
        self.action_cut = QAction(
            QgsApplication.getThemeIcon('/mActionEditCut.svg'), 
            'Cut', self
        )
        self.action_cut.triggered.connect(self.cut_features)
        self.toolbar.addAction(self.action_cut)
        
        # Copy action
        self.action_copy = QAction(
            QgsApplication.getThemeIcon('/mActionEditCopy.svg'), 
            'Copy', self
        )
        self.action_copy.triggered.connect(self.copy_features)
        self.toolbar.addAction(self.action_copy)
        
        # Paste action
        self.action_paste = QAction(
            QgsApplication.getThemeIcon('/mActionEditPaste.svg'), 
            'Paste', self
        )
        self.action_paste.triggered.connect(self.paste_features)
        self.toolbar.addAction(self.action_paste)
        
        self.toolbar.addSeparator()
        
        # Zoom to highlighted
        self.action_zoom = QAction(
            QgsApplication.getThemeIcon('/mActionZoomToSelected.svg'), 
            'Zoom to Highlighted', self
        )
        self.action_zoom.setToolTip('Zoom to highlighted features')
        self.action_zoom.triggered.connect(self.zoom_to_highlighted)
        self.toolbar.addAction(self.action_zoom)
        
        # Refresh
        self.action_refresh = QAction(
            QgsApplication.getThemeIcon('/mActionRefresh.svg'), 
            'Refresh', self
        )
        self.action_refresh.triggered.connect(self.refresh_table)
        self.toolbar.addAction(self.action_refresh)
        
        # Field Calculator
        self.action_field_calc = QAction(
            QgsApplication.getThemeIcon('/mActionCalculateField.svg'), 
            'Field Calculator', self
        )
        self.action_field_calc.setToolTip('Open Field Calculator for targeted features')
        self.action_field_calc.triggered.connect(self.open_field_calculator)
        self.toolbar.addAction(self.action_field_calc)
        
        self.toolbar.addSeparator()
        
        # Dock Attribute Table action
        self.action_dock = QAction(
            self.get_icon('icons/dock_table.png'), 
            'Dock Attribute Table', self
        )
        self.action_dock.setToolTip('Dock this table to QGIS (like original attribute table)')
        self.action_dock.triggered.connect(self.request_dock)
        self.toolbar.addAction(self.action_dock)
    
    def request_dock(self):
        """Request docking of this widget"""
        self.dockRequested.emit()

    def populate_table(self):
        """Populate the table with features from original selection"""
        # Block signals to prevent spurious cellChanged during populate
        # Block signals and disable sorting during populate for performance
        self.table_widget.blockSignals(True)
        self.table_widget.setSortingEnabled(False)
        
        self.table_widget.clear()
        self.row_to_fid.clear()
        self.fid_to_row.clear()
        
        if not self.original_selection:
            self.table_widget.blockSignals(False)
            return
        
        # Get field names
        fields = self.layer.fields()
        field_names = [field.name() for field in fields]
        
        # Setup columns
        self.table_widget.setColumnCount(len(field_names))
        self.table_widget.setHorizontalHeaderLabels(field_names)
        
        # Get features
        request = QgsFeatureRequest().setFilterFids(list(self.original_selection))
        features = list(self.layer.getFeatures(request))
        
        self.table_widget.setRowCount(len(features))
        
        # Determine if cells should be editable
        is_editable = self.layer.isEditable()
        
        for row, feature in enumerate(features):
            fid = feature.id()
            self.row_to_fid[row] = fid
            self.fid_to_row[fid] = row
            
            # Set row number in vertical header
            header_item = QTableWidgetItem(str(row + 1))
            self.table_widget.setVerticalHeaderItem(row, header_item)
            
            for col, field_name in enumerate(field_names):
                value = feature.attribute(field_name)
                item = QTableWidgetItem(str(value) if value is not None else '')
                
                # Store field name for use in cell editing
                item.setData(Qt.UserRole, field_name)
                # Store FID for robust retrieval even after sorting
                item.setData(Qt.UserRole + 1, fid)
                
                # Make cell editable only if layer is in edit mode
                if is_editable:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                
                self.table_widget.setItem(row, col, item)
        
        # Auto-resize columns to content
        self.table_widget.resizeColumnsToContents()
        
        # Unblock signals after population is complete
        # Unblock signals after population is complete
        self.table_widget.setSortingEnabled(True)
        self.table_widget.blockSignals(False)

    def connect_signals(self):
        """Connect layer signals and table signals"""
        self.layer.selectionChanged.connect(self.on_layer_selection_changed)
        self.layer.featuresDeleted.connect(self.on_features_deleted)
        self.layer.editingStarted.connect(self.on_editing_mode_changed)
        self.layer.editingStopped.connect(self.on_editing_mode_changed)
        
        # Connect to selection change signal
        self.table_widget.itemSelectionChanged.connect(self.on_table_selection_changed)
        
        # Connect cell changes for inline editing
        self.table_widget.cellChanged.connect(self.on_cell_changed)

    def on_editing_mode_changed(self):
        """Handle editing mode changes - refresh table to update cell editability"""
        # Preserve highlighted features
        saved_highlights = self.highlighted_features.copy()
        
        self.populate_table()
        
        # Restore highlights
        self.highlighted_features = saved_highlights
        
        # Re-select highlighted rows in table
        self._updating_highlights = True
        try:
            from qgis.PyQt.QtCore import QItemSelectionModel
            selection_model = self.table_widget.selectionModel()
            for fid in self.highlighted_features:
                row = self.get_row_for_fid(fid)
                if row is not None:
                    index = self.table_widget.model().index(row, 0)
                    selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        finally:
            self._updating_highlights = False
        
        self.table_widget.viewport().update()
        self.update_button_states()
        self.update_map_highlighting()
    
    def on_cell_changed(self, row, col):
        """Handle cell value changes - commit to layer"""
        if not self.layer.isEditable():
            return
        
        fid = self.get_fid_for_row(row)
        if fid is None:
            return
        
        item = self.table_widget.item(row, col)
        if item is None:
            return
        
        field_name = item.data(Qt.UserRole)
        if not field_name:
            return
        
        new_value = item.text()
        
        # Get field index
        field_idx = self.layer.fields().indexFromName(field_name)
        if field_idx < 0:
            return
        
        # Update layer attribute
        self.layer.changeAttributeValue(fid, field_idx, new_value if new_value else None)

    def on_table_selection_changed(self):
        """Handle table selection changes - sync with highlighted features"""
        # Skip if we're in programmatic update mode
        if self._updating_highlights:
            return
        
        # Get all selected rows from the table's selection model
        selected_rows = set()
        for index in self.table_widget.selectionModel().selectedRows():
            selected_rows.add(index.row())
        
        # Also check selected items (for when clicking cells)
        for item in self.table_widget.selectedItems():
            selected_rows.add(item.row())
        
        # Convert rows to feature IDs
        new_highlighted = set()
        for row in selected_rows:
            fid = self.get_fid_for_row(row)
            if fid is not None:
                new_highlighted.add(fid)
        
        # Update highlighted features
        if new_highlighted != self.highlighted_features:
            self.highlighted_features = new_highlighted
            # Force repaint to show new colors via delegate
            self.table_widget.viewport().update()
            self.update_info_label()
            self.update_button_states()
            self.update_map_highlighting()
            self.highlightChanged.emit(self.highlighted_features)
            
            # Update last clicked row for shift-click
            if selected_rows:
                self.last_clicked_row = max(selected_rows)

    def get_fid_for_row(self, row):
        """Get feature ID for a given row - robust against sorting"""
        item = self.table_widget.item(row, 0)
        if item:
            return item.data(Qt.UserRole + 1)
        return self.row_to_fid.get(row, None)

    def get_row_for_fid(self, fid):
        """Get row index for a given feature ID - slower but robust against sorting"""
        # Since sorting changes rows, we can't rely on simple map unless we update it on sort
        # But iterating is okay for this table size usually.
        # Alternatively, we could update map on sort, but simpler to search for now or use finding
        if not self.table_widget.isSortingEnabled():
             return self.fid_to_row.get(fid, None)
        
        # If sorted, we must search
        for row in range(self.table_widget.rowCount()):
            if self.get_fid_for_row(row) == fid:
                return row
        return None

    def get_icon(self, icon_name):
        """Get icon from plugin directory"""
        icon_path = os.path.join(self.plugin_dir, icon_name)
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        icon_path = os.path.join(self.plugin_dir, 'icons', icon_name)
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()

    def update_info_label(self):
        """Update the info label with counts"""
        orig = len(self.original_selection)
        high = len(self.highlighted_features)
        
        text = f'<b style="color:#008B8B;">Cyan:</b> {orig}'
        if high > 0:
            text += f' | <b style="color:#DAA520;">Yellow:</b> {high}'
        else:
            text += ' | <span style="color:#888;">Click rows to highlight</span>'
        
        self.info_label.setText(text)

    def update_button_states(self):
        """Update enabled state and tooltips of toolbar buttons"""
        has_highlights = len(self.highlighted_features) > 0
        has_selection = len(self.original_selection) > 0
        has_clipboard = len(self.clipboard_features) > 0
        is_editable = self.layer.isEditable()
        
        # Determine target description for tooltips
        if has_highlights:
            target_count = len(self.highlighted_features)
            target_desc = f"{target_count} highlighted (yellow)"
        else:
            target_count = len(self.original_selection)
            target_desc = f"{target_count} selected (cyan)"
        
        self.action_clear_highlights.setEnabled(has_highlights)
        self.action_highlight_all.setEnabled(has_selection)
        self.action_reselect.setEnabled(has_highlights)
        self.action_select_expr.setEnabled(has_selection)
        self.action_invert.setEnabled(has_selection)
        
        # Destructive actions require edit mode
        can_delete = (has_highlights or has_selection) and is_editable
        self.action_delete.setEnabled(can_delete)
        if is_editable:
            self.action_delete.setToolTip(f'Delete {target_desc} features')
        else:
            self.action_delete.setToolTip(f'Delete {target_desc} features (enable editing first!)')
        
        can_cut = (has_highlights or has_selection) and is_editable
        self.action_cut.setEnabled(can_cut)
        if is_editable:
            self.action_cut.setToolTip(f'Cut {target_desc} features')
        else:
            self.action_cut.setToolTip(f'Cut {target_desc} features (enable editing first!)')
        
        # Copy doesn't require edit mode
        self.action_copy.setEnabled(has_highlights or has_selection)
        self.action_copy.setToolTip(f'Copy {target_desc} features')
        
        # Paste requires edit mode
        can_paste = has_clipboard and is_editable
        self.action_paste.setEnabled(can_paste)
        if is_editable:
            self.action_paste.setToolTip(f'Paste {len(self.clipboard_features)} features')
        else:
            self.action_paste.setToolTip(f'Paste {len(self.clipboard_features)} features (enable editing first!)')
        
        self.action_zoom.setEnabled(has_highlights or has_selection)
        self.action_zoom.setToolTip(f'Zoom to {target_desc} features')
        
        self.action_invert.setToolTip(f'Invert highlights (will highlight {len(self.original_selection) - len(self.highlighted_features)} features)')
        
        # Field calculator requires edit mode for updates
        if hasattr(self, 'action_field_calc'):
            self.action_field_calc.setEnabled(has_highlights or has_selection)
            if is_editable:
                self.action_field_calc.setToolTip(f'Open Field Calculator for {target_desc} features')
            else:
                self.action_field_calc.setToolTip(f'Open Field Calculator for {target_desc} features (read-only preview, enable editing to modify)')

    def get_target_features(self):
        """Get features to operate on (highlighted first, then all)"""
        if self.highlighted_features:
            return self.highlighted_features.copy()
        return self.original_selection.copy()
    
    def update_map_highlighting(self):
        """Update rubber bands on map canvas to show cyan/yellow features"""
        # Clear existing rubber bands
        self.cyan_rubber_band.reset(self.layer.geometryType())
        self.yellow_rubber_band.reset(self.layer.geometryType())
        
        # Get features for cyan (original selection minus highlighted)
        cyan_fids = self.original_selection - self.highlighted_features
        
        # Add cyan geometries (original selection not highlighted)
        if cyan_fids:
            request = QgsFeatureRequest().setFilterFids(list(cyan_fids))
            for feature in self.layer.getFeatures(request):
                geom = feature.geometry()
                if geom and not geom.isNull():
                    self.cyan_rubber_band.addGeometry(geom, self.layer)
        
        # Add yellow geometries (highlighted features)
        if self.highlighted_features:
            request = QgsFeatureRequest().setFilterFids(list(self.highlighted_features))
            for feature in self.layer.getFeatures(request):
                geom = feature.geometry()
                if geom and not geom.isNull():
                    self.yellow_rubber_band.addGeometry(geom, self.layer)
        
        # Refresh canvas
        self.iface.mapCanvas().refresh()
    
    def cleanup_rubber_bands(self):
        """Remove rubber bands from map canvas (called on close)"""
        if hasattr(self, 'cyan_rubber_band') and self.cyan_rubber_band:
            self.cyan_rubber_band.reset()
            self.iface.mapCanvas().scene().removeItem(self.cyan_rubber_band)
        if hasattr(self, 'yellow_rubber_band') and self.yellow_rubber_band:
            self.yellow_rubber_band.reset()
            self.iface.mapCanvas().scene().removeItem(self.yellow_rubber_band)
        self.iface.mapCanvas().refresh()
    
    def reselect_to_highlighted(self):
        """Narrow selection down to highlighted features only"""
        if not self.highlighted_features:
            self.iface.messageBar().pushInfo('Selection', 'No features highlighted to re-select.')
            return
        
        # Make highlighted become the new original selection
        self.original_selection = self.highlighted_features.copy()
        self.highlighted_features.clear()
        
        # Update layer selection
        self._updating_selection = True
        self.layer.selectByIds(list(self.original_selection))
        self._updating_selection = False
        
        # Refresh table with new selection
        self.populate_table()
        self.table_widget.viewport().update()
        self.update_info_label()
        self.update_button_states()
        self.update_map_highlighting()
        
        self.iface.messageBar().pushSuccess(
            'Re-select', 
            f'Selection narrowed to {len(self.original_selection)} features.'
        )

    # ==================== Actions ====================

    def clear_highlights(self):
        """Clear all yellow highlights"""
        if not self.highlighted_features:
            return
        count = len(self.highlighted_features)
        self.highlighted_features.clear()
        self.last_clicked_row = None
        self.table_widget.clearSelection()
        self.table_widget.viewport().update()
        self.update_info_label()
        self.update_button_states()
        self.update_map_highlighting()
        self.iface.messageBar().pushInfo('Selection', f'Cleared {count} highlights.')

    def highlight_all(self):
        """Highlight all features"""
        self.highlighted_features = self.original_selection.copy()
        self.table_widget.selectAll()
        self.table_widget.viewport().update()
        self.update_info_label()
        self.update_button_states()
        self.update_map_highlighting()
        self.iface.messageBar().pushSuccess('Selection', f'Highlighted {len(self.highlighted_features)} features.')

    def select_by_expression(self):
        """Open custom filter dialog that only shows values from selected features"""
        if not self.original_selection:
            self.iface.messageBar().pushInfo('Filter', 'No features selected to filter.')
            return
        
        # Use our custom dialog that only shows values from cyan selection
        dialog = SelectionFilterDialog(self.layer, self.original_selection, self)
        
        if dialog.exec_() == QDialog.Accepted:
            expr_text = dialog.get_expression()
            if expr_text:
                from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
                
                # Create and prepare expression
                expr = QgsExpression(expr_text)
                if expr.hasParserError():
                    self.iface.messageBar().pushCritical('Filter', f'Expression error: {expr.parserErrorString()}')
                    return
                
                # Create context
                context = QgsExpressionContext()
                context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(self.layer))
                
                # Get features from selection and evaluate manually
                request = QgsFeatureRequest().setFilterFids(list(self.original_selection))
                matching_fids = set()
                
                for feature in self.layer.getFeatures(request):
                    context.setFeature(feature)
                    result = expr.evaluate(context)
                    if result:
                        matching_fids.add(feature.id())
                
                self.highlighted_features = matching_fids
                
                # Use selection model to select multiple rows
                # Block the signal handler during programmatic changes
                from qgis.PyQt.QtCore import QItemSelectionModel
                self._updating_highlights = True
                try:
                    self.table_widget.clearSelection()
                    selection_model = self.table_widget.selectionModel()
                    for fid in matching_fids:
                        row = self.get_row_for_fid(fid)
                        if row is not None:
                            index = self.table_widget.model().index(row, 0)
                            selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                finally:
                    self._updating_highlights = False
                
                self.table_widget.viewport().update()
                self.update_info_label()
                self.update_button_states()
                self.update_map_highlighting()
                self.iface.messageBar().pushSuccess('Filter', f'Highlighted {len(matching_fids)} features.')

    def invert_highlights(self):
        """Invert highlights within original selection"""
        if not self.original_selection:
            return
        
        self.highlighted_features = self.original_selection - self.highlighted_features
        
        # Use selection model to select multiple rows
        # Block the signal handler during programmatic changes
        from qgis.PyQt.QtCore import QItemSelectionModel
        self._updating_highlights = True
        try:
            self.table_widget.clearSelection()
            selection_model = self.table_widget.selectionModel()
            for fid in self.highlighted_features:
                row = self.get_row_for_fid(fid)
                if row is not None:
                    index = self.table_widget.model().index(row, 0)
                    selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        finally:
            self._updating_highlights = False
        
        self.table_widget.viewport().update()
        self.update_info_label()
        self.update_button_states()
        self.update_map_highlighting()
        self.iface.messageBar().pushInfo('Selection', f'Inverted: {len(self.highlighted_features)} highlighted.')

    def delete_features(self):
        """Delete target features"""
        fids = self.get_target_features()
        if not fids:
            return
        
        target_type = "highlighted" if self.highlighted_features else "all selected"
        
        reply = QMessageBox.question(
            self, 'Delete Features',
            f'Delete {len(fids)} {target_type} features?',
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        was_editing = self.layer.isEditable()
        if not was_editing:
            self.layer.startEditing()
        
        if self.layer.deleteFeatures(list(fids)):
            if not was_editing:
                self.layer.commitChanges()
            
            self.original_selection -= fids
            self.highlighted_features -= fids
            
            self.populate_table()
            self.table_widget.viewport().update()
            self.update_info_label()
            self.update_button_states()
            
            self._updating_selection = True
            self.layer.selectByIds(list(self.original_selection))
            self._updating_selection = False
            
            self.iface.messageBar().pushSuccess('Delete', f'Deleted {len(fids)} features.')
        else:
            if not was_editing:
                self.layer.rollBack()
            QMessageBox.warning(self, 'Error', 'Failed to delete features.')

    def cut_features(self):
        """Cut features"""
        self.copy_features()
        self.delete_features()

    def copy_features(self):
        """Copy target features"""
        fids = self.get_target_features()
        if not fids:
            return
        
        self.clipboard_features = []
        request = QgsFeatureRequest().setFilterFids(list(fids))
        for feature in self.layer.getFeatures(request):
            self.clipboard_features.append(QgsFeature(feature))
        
        self.update_button_states()
        self.iface.messageBar().pushSuccess('Copy', f'Copied {len(self.clipboard_features)} features.')

    def paste_features(self):
        """Paste features"""
        if not self.clipboard_features:
            return
        
        was_editing = self.layer.isEditable()
        if not was_editing:
            self.layer.startEditing()
        
        success, new_features = self.layer.dataProvider().addFeatures(self.clipboard_features)
        
        if success:
            if not was_editing:
                self.layer.commitChanges()
            self.iface.messageBar().pushSuccess('Paste', f'Pasted {len(new_features)} features.')
            self.refresh_table()
        else:
            if not was_editing:
                self.layer.rollBack()
            QMessageBox.warning(self, 'Error', 'Failed to paste features.')

    def zoom_to_highlighted(self):
        """Zoom to target features"""
        fids = self.get_target_features()
        if not fids:
            return
        
        self._updating_selection = True
        self.layer.selectByIds(list(fids))
        self._updating_selection = False
        
        self.iface.mapCanvas().zoomToSelected(self.layer)

    def open_field_calculator(self):
        """Open field calculator for targeted features"""
        fids = self.get_target_features()
        if not fids and not self.original_selection:
            self.iface.messageBar().pushInfo('Field Calculator', 'No features selected.')
            return

    # ==================== Context Menu ====================

    def show_context_menu(self, pos):
        """Show context menu for table"""
        item = self.table_widget.itemAt(pos)
        if not item:
            return
        
        menu = QMenu(self)
        
        # feature actions
        zoom_action = menu.addAction(QgsApplication.getThemeIcon('/mActionZoomToSelected.svg'), 'Zoom to Feature')
        pan_action = menu.addAction(QgsApplication.getThemeIcon('/mActionPan.svg'), 'Pan to Feature')
        flash_action = menu.addAction('Flash Feature')
        menu.addSeparator()
        copy_id_action = menu.addAction('Copy Feature ID')
        
        action = menu.exec_(self.table_widget.mapToGlobal(pos))
        
        if not action:
            return
            
        row = item.row()
        fid = self.get_fid_for_row(row)
        
        if fid is not None:
            if action == zoom_action:
                self.zoom_to_fid(fid)
            elif action == pan_action:
                self.pan_to_fid(fid)
            elif action == flash_action:
                self.flash_fid(fid)
            elif action == copy_id_action:
                QApplication.clipboard().setText(str(fid))
                self.iface.messageBar().pushInfo('Copy', f'Feature ID {fid} copied.')

    def zoom_to_fid(self, fid):
        """Zoom to specific feature ID"""
        box = self.layer.getFeature(fid).geometry().boundingBox()
        self.iface.mapCanvas().setExtent(box)
        self.iface.mapCanvas().refresh()

    def pan_to_fid(self, fid):
        """Pan to specific feature ID"""
        point = self.layer.getFeature(fid).geometry().centroid().asPoint()
        self.iface.mapCanvas().setCenter(point)
        self.iface.mapCanvas().refresh()

    def flash_fid(self, fid):
        """Flash specific feature ID"""
        self.iface.mapCanvas().flashFeatureIds(self.layer, [fid])
        
        # Pass both highlighted and all selected, so user can choose
        target_fids = fids if fids else self.original_selection
        dialog = FieldCalculatorDialog(self.layer, target_fids, self.original_selection, self)
        
        if dialog.exec_() == QDialog.Accepted:
            expr_text = dialog.get_expression()
            field_name, is_new, field_type = dialog.get_output_field()
            active_fids = dialog.get_active_fids()  # Respects checkbox state
            
            if not expr_text or not field_name:
                self.iface.messageBar().pushWarning('Field Calculator', 'Missing expression or field name.')
                return
            
            # Check if layer is editable
            was_editing = self.layer.isEditable()
            if not was_editing:
                self.layer.startEditing()
            
            try:
                from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsField
                from qgis.PyQt.QtCore import QVariant
                
                # Create new field if needed
                if is_new:
                    if field_type == 'String':
                        qfield = QgsField(field_name, QVariant.String, 'string', 254)
                    elif field_type == 'Integer':
                        qfield = QgsField(field_name, QVariant.Int, 'integer')
                    else:  # Double
                        qfield = QgsField(field_name, QVariant.Double, 'double')
                    
                    if not self.layer.dataProvider().addAttributes([qfield]):
                        raise Exception("Failed to add new field")
                    self.layer.updateFields()
                
                # Get field index
                field_idx = self.layer.fields().indexFromName(field_name)
                if field_idx < 0:
                    raise Exception(f"Field '{field_name}' not found")
                
                # Create expression
                expr = QgsExpression(expr_text)
                if expr.hasParserError():
                    raise Exception(f"Expression error: {expr.parserErrorString()}")
                
                context = QgsExpressionContext()
                context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(self.layer))
                
                # Update only active features (from dialog)
                request = QgsFeatureRequest().setFilterFids(list(active_fids))
                updated_count = 0
                
                for feature in self.layer.getFeatures(request):
                    context.setFeature(feature)
                    result = expr.evaluate(context)
                    
                    if expr.hasEvalError():
                        continue
                    
                    self.layer.changeAttributeValue(feature.id(), field_idx, result)
                    updated_count += 1
                
                if not was_editing:
                    self.layer.commitChanges()
                
                self.refresh_table()
                self.iface.messageBar().pushSuccess(
                    'Field Calculator', 
                    f'Updated {updated_count} features in field "{field_name}".'
                )
                
            except Exception as e:
                if not was_editing:
                    self.layer.rollBack()
                QMessageBox.critical(self, 'Field Calculator Error', str(e))


    def refresh_table(self):
        """Refresh the table from layer - syncs with current layer selection"""
        current_selection = set(self.layer.selectedFeatureIds())
        
        if current_selection:
            self.original_selection = current_selection
        
        self.highlighted_features &= self.original_selection
        
        self.populate_table()
        self.table_widget.viewport().update()
        self.update_info_label()
        self.update_button_states()
        self.update_map_highlighting()

    # ==================== Signal Handlers ====================

    def on_layer_selection_changed(self, selected, deselected, clearAndSelect):
        """Handle layer selection changes from outside (e.g., from main attribute table)
        
        This provides seamless two-way synchronization:
        - When user changes selection in main QGIS, this updates cyan rows here
        - When user uses Re-select here, the layer selection is updated there
        """
        if self._updating_selection:
            return
        
        new_selection = set(self.layer.selectedFeatureIds())
        
        # Only update if selection actually changed
        if new_selection != self.original_selection:
            self.original_selection = new_selection
            # Keep only highlights that are still in the new selection
            self.highlighted_features &= self.original_selection
            
            # Refresh table with new selection
            self.populate_table()
            self.table_widget.viewport().update()
            self.update_info_label()
            self.update_button_states()
            
            # Update map highlighting to reflect new selection
            self.update_map_highlighting()
            
            # Notify user of sync
            self.iface.messageBar().pushInfo(
                'Sync', 
                f'Selection updated: {len(self.original_selection)} features'
            )

    def on_features_deleted(self, fids):
        """Handle features deleted from layer"""
        deleted = set(fids)
        self.original_selection -= deleted
        self.highlighted_features -= deleted
        self.populate_table()
        self.table_widget.viewport().update()
        self.update_info_label()
        self.update_button_states()
        self.update_map_highlighting()


class AdvancedSelectionDock(QDockWidget):
    """Dockable wrapper for the Advanced Selection Widget"""
    
    closed = pyqtSignal()
    undockRequested = pyqtSignal()  # Signal to convert back to floating dialog
    
    def __init__(self, layer, iface, plugin_dir, parent=None):
        super().__init__(f'Selection Table - {layer.name()}', parent)
        self.layer = layer
        self.iface = iface
        self.plugin_dir = plugin_dir
        
        # Set dock features
        self.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea | 
                            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetClosable | 
                        QDockWidget.DockWidgetMovable | 
                        QDockWidget.DockWidgetFloatable)
        
        # Create the main widget
        self.selection_widget = AdvancedSelectionWidget(layer, iface, plugin_dir, self)
        self.setWidget(self.selection_widget)
        
        # Hide the dock button (already docked) and replace with undock button
        self.selection_widget.action_dock.setVisible(False)
        
        # Add undock action to toolbar
        self.action_undock = QAction(
            QIcon(os.path.join(plugin_dir, 'icons', 'undock.png')),
            'Undock (Float Window)', self.selection_widget
        )
        self.action_undock.setToolTip('Convert to floating window')
        self.action_undock.triggered.connect(self.request_undock)
        self.selection_widget.toolbar.addAction(self.action_undock)
        
        # Set minimum size
        self.setMinimumWidth(400)
        self.setMinimumHeight(200)
    
    def request_undock(self):
        """Request conversion to floating dialog"""
        self.undockRequested.emit()
    
    def closeEvent(self, event):
        """Handle close event"""
        # Clean up rubber bands from map canvas
        self.selection_widget.cleanup_rubber_bands()
        
        # Restore original selection on close
        if self.selection_widget.original_selection:
            self.selection_widget._updating_selection = True
            self.layer.selectByIds(list(self.selection_widget.original_selection))
            self.selection_widget._updating_selection = False
        
        self.closed.emit()
        event.accept()


# Keep backward compatibility with dialog mode
class AdvancedSelectionDialog(QDialog):
    """Dialog wrapper for standalone mode"""
    
    highlightChanged = pyqtSignal(set)
    dockRequested = pyqtSignal()  # Signal to convert to dock
    
    def __init__(self, layer, iface, plugin_dir, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.iface = iface
        self.plugin_dir = plugin_dir
        self.setWindowTitle(f'Advanced Selection Table - {layer.name()}')
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.resize(1100, 650)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
        self.selection_widget = AdvancedSelectionWidget(layer, iface, plugin_dir, self)
        layout.addWidget(self.selection_widget)
        
        self.selection_widget.highlightChanged.connect(self.highlightChanged.emit)
        self.selection_widget.dockRequested.connect(self.on_dock_requested)
    
    def on_dock_requested(self):
        """Handle dock request from widget - emit signal for plugin to handle"""
        self.dockRequested.emit()
    
    @property
    def original_selection(self):
        return self.selection_widget.original_selection
    
    @property
    def highlighted_features(self):
        return self.selection_widget.highlighted_features
    
    def closeEvent(self, event):
        """Restore original selection on close and cleanup rubber bands"""
        self._do_cleanup()
        event.accept()
    
    def reject(self):
        """Handle dialog rejection (X button, Escape key)"""
        self._do_cleanup()
        super().reject()
    
    def _do_cleanup(self):
        """Internal cleanup method - called from both closeEvent and reject"""
        try:
            # Clean up rubber bands from map canvas
            if hasattr(self, 'selection_widget') and self.selection_widget:
                self.selection_widget.cleanup_rubber_bands()
                
                # Restore original selection
                if self.selection_widget.original_selection:
                    self.selection_widget._updating_selection = True
                    self.layer.selectByIds(list(self.selection_widget.original_selection))
                    self.selection_widget._updating_selection = False
        except Exception:
            pass  # Fail silently during cleanup
