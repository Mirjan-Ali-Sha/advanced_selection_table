# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QFrame, QGroupBox, QFormLayout, 
    QLineEdit, QComboBox, QSpinBox, QTabWidget, QTextEdit, QTreeWidget, QTreeWidgetItem, 
    QLabel, QPushButton, QSplitter, QWidget, QMessageBox, QListWidget, QListWidgetItem
)
from qgis.core import QgsFeatureRequest, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsMessageLog, Qgis

class FieldCalculatorDialog(QDialog):
    """
    QGIS-style Field Calculator for targeted feature updates.
    Matches the layout/functionality of QGIS default Field Calculator
    but only updates highlighted (yellow) or selected (cyan) features.
    """
    
    def __init__(self, layer, target_fids, all_selection_fids=None, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.target_fids = set(target_fids)  # Highlighted subset
        self.all_selection_fids = set(all_selection_fids) if all_selection_fids else set(target_fids)  # All cyan
        self.active_fids = list(self.target_fids)  # Currently active for operation
        self.current_feature_idx = 0
        
        self.setWindowTitle(f'{layer.name()} — Field Calculator')
        self.setMinimumSize(850, 650)
        self.setup_ui()
        self.load_fields()
        self.update_preview()
    
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)
        self.setLayout(main_layout)
        
        # ================== TOP: Target info ==================
        has_highlights = len(self.target_fids) < len(self.all_selection_fids)
        if has_highlights:
            self.target_checkbox = QCheckBox(f"Only update {len(self.target_fids)} highlighted feature(s) (uncheck to update all {len(self.all_selection_fids)} selected)")
            self.target_checkbox.setChecked(True)
            self.target_checkbox.setEnabled(True)
            self.target_checkbox.toggled.connect(self.on_target_mode_changed)
        else:
            self.target_checkbox = QCheckBox(f"Update all {len(self.all_selection_fids)} selected feature(s)")
            self.target_checkbox.setChecked(True)
            self.target_checkbox.setEnabled(False)
        self.target_checkbox.setStyleSheet("font-weight: bold; color: #1976D2;")
        main_layout.addWidget(self.target_checkbox)
        
        # ================== Field Output Options ==================
        options_frame = QFrame()
        options_frame.setFrameShape(QFrame.StyledPanel)
        options_layout = QHBoxLayout(options_frame)
        options_layout.setSpacing(20)
        
        # LEFT: Create new field
        new_field_group = QGroupBox("Create a new field")
        new_field_group.setCheckable(True)
        new_field_group.setChecked(False)
        new_field_group.toggled.connect(self.on_create_mode_toggled)
        self.new_field_group = new_field_group
        
        new_layout = QFormLayout()
        new_layout.setSpacing(4)
        
        self.new_field_name = QLineEdit()
        self.new_field_name.setPlaceholderText("field_name")
        new_layout.addRow("Output field name:", self.new_field_name)
        
        self.new_field_type = QComboBox()
        self.new_field_type.addItems([
            "Text (string)", "Whole number (integer)", "Decimal number (double)",
            "Date", "Boolean"
        ])
        new_layout.addRow("Output field type:", self.new_field_type)
        
        length_layout = QHBoxLayout()
        self.new_field_length = QSpinBox()
        self.new_field_length.setRange(1, 254)
        self.new_field_length.setValue(50)
        length_layout.addWidget(self.new_field_length)
        length_layout.addWidget(QLabel("Precision"))
        self.new_field_precision = QSpinBox()
        self.new_field_precision.setRange(0, 15)
        self.new_field_precision.setValue(3)
        length_layout.addWidget(self.new_field_precision)
        length_layout.addStretch()
        new_layout.addRow("Output field length:", length_layout)
        
        new_field_group.setLayout(new_layout)
        options_layout.addWidget(new_field_group, 1)
        
        # RIGHT: Update existing field
        update_group = QGroupBox("Update existing field")
        update_group.setCheckable(True)
        update_group.setChecked(True)
        update_group.toggled.connect(self.on_update_mode_toggled)
        self.update_group = update_group
        
        update_layout = QVBoxLayout()
        self.field_combo = QComboBox()
        update_layout.addWidget(self.field_combo)
        update_layout.addStretch()
        update_group.setLayout(update_layout)
        options_layout.addWidget(update_group, 1)
        
        main_layout.addWidget(options_frame)
        
        # ================== MIDDLE: Expression Builder ==================
        expr_splitter = QSplitter(Qt.Horizontal)
        
        # LEFT PANEL: Expression text + operators
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Expression header with tabs (simplified - just Expression)
        expr_tabs = QTabWidget()
        
        expr_widget = QWidget()
        expr_tab_layout = QVBoxLayout(expr_widget)
        expr_tab_layout.setContentsMargins(4, 4, 4, 4)
        
        self.expr_edit = QTextEdit()
        self.expr_edit.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                background-color: #FFFEF0;
                border: 1px solid #ccc;
            }
        """)
        self.expr_edit.setPlaceholderText("Expression...")
        self.expr_edit.textChanged.connect(self.on_expression_changed)
        expr_tab_layout.addWidget(self.expr_edit, 1)
        
        # Operator buttons
        ops_layout = QHBoxLayout()
        ops_layout.setSpacing(2)
        for op in ['=', '+', '-', '/', '*', '^', '||', '(', ')', "'\\n'"]:
            btn = QPushButton(op)
            btn.setFixedSize(28, 24)
            btn.setStyleSheet("font-size: 11px; padding: 0;")
            btn.clicked.connect(lambda checked, o=op: self.insert_operator(o))
            ops_layout.addWidget(btn)
        ops_layout.addStretch()
        expr_tab_layout.addLayout(ops_layout)
        
        # Feature navigation + Preview
        nav_layout = QHBoxLayout()
        nav_layout.addWidget(QLabel("Feature"))
        self.feature_combo = QComboBox()
        self.feature_combo.setMinimumWidth(100)
        self.feature_combo.currentIndexChanged.connect(self.on_feature_changed)
        nav_layout.addWidget(self.feature_combo)
        
        prev_btn = QPushButton("◀")
        prev_btn.setFixedWidth(24)
        prev_btn.clicked.connect(self.prev_feature)
        nav_layout.addWidget(prev_btn)
        
        next_btn = QPushButton("▶")
        next_btn.setFixedWidth(24)
        next_btn.clicked.connect(self.next_feature)
        nav_layout.addWidget(next_btn)
        nav_layout.addStretch()
        expr_tab_layout.addLayout(nav_layout)
        
        # Preview label
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("Preview:"))
        self.preview_label = QLabel("")
        self.preview_label.setStyleSheet("color: #666; font-style: italic;")
        preview_layout.addWidget(self.preview_label, 1)
        expr_tab_layout.addLayout(preview_layout)
        
        expr_tabs.addTab(expr_widget, "Expression")
        left_layout.addWidget(expr_tabs)
        
        expr_splitter.addWidget(left_panel)
        
        # CENTER PANEL: Field list
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        # Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔎"))
        self.field_search = QLineEdit()
        self.field_search.setPlaceholderText("Search...")
        self.field_search.textChanged.connect(self.filter_fields)
        search_layout.addWidget(self.field_search)
        center_layout.addLayout(search_layout)
        
        # Field list
        self.field_list = QListWidget()
        self.field_list.setStyleSheet("font-family: monospace; font-size: 11px;")
        self.field_list.itemDoubleClicked.connect(self.on_field_double_clicked)
        self.field_list.itemClicked.connect(self.on_field_clicked)
        center_layout.addWidget(self.field_list)
        
        # Function categories (expandable tree)
        self.func_tree = QTreeWidget()
        self.func_tree.setHeaderHidden(True)
        self.func_tree.setStyleSheet("font-size: 11px;")
        
        # Conditionals
        cond_item = QTreeWidgetItem(["▾ Conditionals"])
        for func in ["if(condition, true, false)", "CASE WHEN...THEN...END", "coalesce(a, b)", 
                     "nullif(a, b)", "try(expr)"]:
            child = QTreeWidgetItem([func])
            child.setData(0, Qt.UserRole, func.split("(")[0] + "()" if "(" in func else func)
            cond_item.addChild(child)
        self.func_tree.addTopLevelItem(cond_item)
        
        # String Functions
        str_item = QTreeWidgetItem(["▾ String Functions"])
        for func in ["upper(str)", "lower(str)", "length(str)", "substr(str,start,len)", 
                     "concat(a,b)", "replace(str,old,new)", "trim(str)", "left(str,n)", "right(str,n)"]:
            child = QTreeWidgetItem([func])
            child.setData(0, Qt.UserRole, func)
            str_item.addChild(child)
        self.func_tree.addTopLevelItem(str_item)
        
        # Math Functions  
        math_item = QTreeWidgetItem(["▾ Math Functions"])
        for func in ["abs(x)", "round(x,n)", "floor(x)", "ceil(x)", "sqrt(x)", 
                     "sin(x)", "cos(x)", "tan(x)", "log(x)", "exp(x)", "pow(x,y)"]:
            child = QTreeWidgetItem([func])
            child.setData(0, Qt.UserRole, func)
            math_item.addChild(child)
        self.func_tree.addTopLevelItem(math_item)
        
        # Date/Time Functions
        date_item = QTreeWidgetItem(["▾ Date/Time Functions"])
        for func in ["now()", "day(date)", "month(date)", "year(date)", 
                     "hour(datetime)", "minute(datetime)", "second(datetime)", "to_date(str)"]:
            child = QTreeWidgetItem([func])
            child.setData(0, Qt.UserRole, func)
            date_item.addChild(child)
        self.func_tree.addTopLevelItem(date_item)
        
        # Geometry Functions
        geom_item = QTreeWidgetItem(["▾ Geometry Functions"])
        for func in ["$area", "$length", "$perimeter", "$x", "$y", 
                     "centroid($geometry)", "buffer($geometry,dist)", "area($geometry)"]:
            child = QTreeWidgetItem([func])
            child.setData(0, Qt.UserRole, func)
            geom_item.addChild(child)
        self.func_tree.addTopLevelItem(geom_item)
        
        # Expand all by default
        self.func_tree.expandAll()
        self.func_tree.itemDoubleClicked.connect(self.on_func_double_clicked)
        self.func_tree.itemClicked.connect(self.on_func_clicked)
        center_layout.addWidget(self.func_tree)
        
        expr_splitter.addWidget(center_panel)
        
        # RIGHT PANEL: Help + Values
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Help text
        self.help_text = QLabel()
        self.help_text.setWordWrap(True)
        self.help_text.setStyleSheet("""
            background-color: #FFF8DC; 
            padding: 8px; 
            border: 1px solid #E0D8B8;
            color: #8B4513;
        """)
        self.help_text.setText("<b>group field</b><br><br>Double-click to add field name to expression string.<br><br>Right-Click on field name to open context menu sample value loading options.")
        self.help_text.setMinimumHeight(80)
        right_layout.addWidget(self.help_text)
        
        # Values section
        values_group = QGroupBox("Values")
        values_layout = QVBoxLayout(values_group)
        
        self.value_search = QLineEdit()
        self.value_search.setPlaceholderText("Search...")
        self.value_search.textChanged.connect(self.filter_values)
        values_layout.addWidget(self.value_search)
        
        btn_layout = QHBoxLayout()
        all_unique_btn = QPushButton("All Unique")
        all_unique_btn.clicked.connect(self.load_all_unique_values)
        btn_layout.addWidget(all_unique_btn)
        
        samples_btn = QPushButton("10 Samples")
        samples_btn.clicked.connect(self.load_sample_values)
        btn_layout.addWidget(samples_btn)
        values_layout.addLayout(btn_layout)
        
        self.value_list = QListWidget()
        self.value_list.setStyleSheet("font-size: 11px;")
        self.value_list.itemDoubleClicked.connect(self.on_value_double_clicked)
        values_layout.addWidget(self.value_list)
        
        right_layout.addWidget(values_group, 1)
        
        expr_splitter.addWidget(right_panel)
        
        # Set splitter sizes
        expr_splitter.setSizes([350, 200, 250])
        main_layout.addWidget(expr_splitter, 1)
        
        # ================== BOTTOM: Buttons ==================
        # Info message (like QGIS)
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #E3F2FD; padding: 8px; border-radius: 4px;")
        info_layout = QHBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 4, 8, 4)
        info_icon = QLabel("ℹ️")
        info_layout.addWidget(info_icon)
        info_text = QLabel(f"Only the {len(self.target_fids)} targeted features will be updated. "
                          "Non-targeted features will retain their current values.")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text, 1)
        main_layout.addWidget(info_frame)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.setMinimumWidth(80)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("Apply")
        apply_btn.setMinimumWidth(80)
        apply_btn.clicked.connect(self.apply_changes)
        button_layout.addWidget(apply_btn)
        
        main_layout.addLayout(button_layout)
    
    def load_fields(self):
        """Load field names into list and combo"""
        self.field_combo.clear()
        self.field_list.clear()
        self.feature_combo.clear()
        
        # Type prefixes like QGIS
        type_prefixes = {
            'String': 'abc',
            'Integer': '123',
            'Real': '1.2',
            'Double': '1.2',
            'Date': '📅',
            'DateTime': '📅',
        }
        
        for field in self.layer.fields():
            type_name = field.typeName()
            prefix = type_prefixes.get(type_name, '?')
            
            # Add to combo (for update existing)
            self.field_combo.addItem(f"{prefix} {field.name()}", field.name())
            
            # Add to list (for expression builder)
            item = QListWidgetItem(f"{prefix} {field.name()}")
            item.setData(Qt.UserRole, field.name())
            self.field_list.addItem(item)
        
        # Load feature names for preview navigation
        request = QgsFeatureRequest().setFilterFids(self.active_fids[:100])  # Limit for performance
        for feature in self.layer.getFeatures(request):
            # Try to get a display value
            display = str(feature.id())
            for fname in ['NAME', 'name', 'Name', 'OBJECTID', 'ID', 'id']:
                if fname in [f.name() for f in self.layer.fields()]:
                    val = feature.attribute(fname)
                    if val:
                        display = str(val)
                        break
            self.feature_combo.addItem(display, feature.id())
    
    def on_create_mode_toggled(self, checked):
        if checked and self.update_group.isChecked():
            self.update_group.setChecked(False)
        elif not checked and not self.update_group.isChecked():
            self.update_group.setChecked(True)
    
    def on_update_mode_toggled(self, checked):
        if checked and self.new_field_group.isChecked():
            self.new_field_group.setChecked(False)
        elif not checked and not self.new_field_group.isChecked():
            self.new_field_group.setChecked(True)
    
    def insert_operator(self, op):
        if op == "'\\n'":
            op = "\\n"
        self.expr_edit.insertPlainText(f" {op} ")
    
    def filter_fields(self, text):
        for i in range(self.field_list.count()):
            item = self.field_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())
    
    def filter_values(self, text):
        for i in range(self.value_list.count()):
            item = self.value_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())
    
    def on_field_clicked(self, item):
        field_name = item.data(Qt.UserRole)
        self.help_text.setText(f"<b>{field_name}</b><br><br>Double-click to add field name to expression string.")
        self.current_field = field_name
    
    def on_field_double_clicked(self, item):
        field_name = item.data(Qt.UserRole)
        self.expr_edit.insertPlainText(f'"{field_name}"')
    
    def on_func_clicked(self, item, column=0):
        """Show help for clicked function"""
        func_text = item.text(0)
        if item.parent() is None:
            # Category header clicked
            if "Conditional" in func_text:
                self.help_text.setText("<b>Conditionals:</b><br>if(condition, true, false) - returns true value if condition is true, else false value<br><br>CASE WHEN...THEN...END - multiple conditions<br><br>coalesce(a, b) - returns first non-null value")
            elif "String" in func_text:
                self.help_text.setText("<b>String Functions:</b><br>upper(), lower(), length(), substr(), concat(), replace(), trim()")
            elif "Math" in func_text:
                self.help_text.setText("<b>Math Functions:</b><br>abs(), round(), floor(), ceil(), sqrt(), sin(), cos(), tan()")
            elif "Date" in func_text:
                self.help_text.setText("<b>Date/Time Functions:</b><br>now(), day(), month(), year(), hour(), minute()")
            elif "Geometry" in func_text:
                self.help_text.setText("<b>Geometry Functions:</b><br>$area, $length, $perimeter, $x, $y, centroid()")
        else:
            # Function item clicked - show specific help
            self.help_text.setText(f"<b>{func_text}</b><br><br>Double-click to insert into expression.")
    
    def on_func_double_clicked(self, item, column=0):
        """Insert function into expression"""
        if item.parent() is not None:
            # Only insert child items (actual functions)
            func_data = item.data(0, Qt.UserRole)
            if func_data:
                self.expr_edit.insertPlainText(func_data)
    
    def on_target_mode_changed(self, checked):
        """Toggle between updating highlighted only vs all selected"""
        if checked:
            self.active_fids = list(self.target_fids)
        else:
            self.active_fids = list(self.all_selection_fids)
        
        # Reload features for preview
        self.feature_combo.clear()
        request = QgsFeatureRequest().setFilterFids(self.active_fids[:100])
        for feature in self.layer.getFeatures(request):
            display = str(feature.id())
            for fname in ['NAME', 'name', 'Name', 'OBJECTID', 'ID', 'id']:
                if fname in [f.name() for f in self.layer.fields()]:
                    val = feature.attribute(fname)
                    if val:
                        display = str(val)
                        break
            self.feature_combo.addItem(display, feature.id())
        
        self.update_preview()
    
    def on_value_double_clicked(self, item):
        value = item.data(Qt.UserRole)
        if isinstance(value, str):
            self.expr_edit.insertPlainText(f"'{value}'")
        else:
            self.expr_edit.insertPlainText(str(value))
    
    def load_all_unique_values(self):
        self.value_list.clear()
        if not hasattr(self, 'current_field'):
            return
        
        # Get unique values from targeted features
        values = set()
        request = QgsFeatureRequest().setFilterFids(self.active_fids)
        for feature in self.layer.getFeatures(request):
            val = feature.attribute(self.current_field)
            if val is not None:
                values.add(val)
        
        for val in sorted(values, key=str)[:100]:  # Limit display
            item = QListWidgetItem(str(val))
            item.setData(Qt.UserRole, val)
            self.value_list.addItem(item)
    
    def load_sample_values(self):
        self.value_list.clear()
        if not hasattr(self, 'current_field'):
            return
        
        # Get sample values
        request = QgsFeatureRequest().setFilterFids(self.active_fids[:10])
        for feature in self.layer.getFeatures(request):
            val = feature.attribute(self.current_field)
            if val is not None:
                item = QListWidgetItem(str(val))
                item.setData(Qt.UserRole, val)
                self.value_list.addItem(item)
    
    def on_feature_changed(self, index):
        self.current_feature_idx = index
        self.update_preview()
    
    def prev_feature(self):
        if self.current_feature_idx > 0:
            self.feature_combo.setCurrentIndex(self.current_feature_idx - 1)
    
    def next_feature(self):
        if self.current_feature_idx < self.feature_combo.count() - 1:
            self.feature_combo.setCurrentIndex(self.current_feature_idx + 1)
    
    def on_expression_changed(self):
        self.update_preview()
    
    def update_preview(self):
        expr_text = self.expr_edit.toPlainText().strip()
        if not expr_text:
            self.preview_label.setText("")
            self.preview_label.setStyleSheet("color: #666;")
            return
        
        fid = self.feature_combo.currentData()
        if fid is None:
            return
        
        try:
            expr = QgsExpression(expr_text)
            if expr.hasParserError():
                self.preview_label.setText(f"❌ {expr.parserErrorString()}")
                self.preview_label.setStyleSheet("color: #c62828;")
                return
            
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(self.layer))
            
            feature = self.layer.getFeature(fid)
            context.setFeature(feature)
            result = expr.evaluate(context)
            
            if expr.hasEvalError():
                self.preview_label.setText(f"❌ {expr.evalErrorString()}")
                self.preview_label.setStyleSheet("color: #c62828;")
            else:
                self.preview_label.setText(str(result))
                self.preview_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        except Exception as e:
            self.preview_label.setText(f"❌ Error: {str(e)}")
            self.preview_label.setStyleSheet("color: #c62828;")
    
    def apply_changes(self):
        """Apply changes without closing dialog"""
        # This would apply the changes
        # For now, just show a message
        QgsMessageLog.logMessage("Apply clicked", "AdvancedSelection", Qgis.Info)
    
    def get_output_field(self):
        """Get output field name and whether it's new"""
        if self.new_field_group.isChecked():
            type_map = {
                "Text (string)": "String",
                "Whole number (integer)": "Integer", 
                "Decimal number (double)": "Double",
                "Date": "Date",
                "Boolean": "Boolean"
            }
            return (self.new_field_name.text().strip(), 
                    True, 
                    type_map.get(self.new_field_type.currentText(), "String"))
        else:
            return self.field_combo.currentData(), False, None
    
    def get_expression(self):
        """Get the expression text"""
        return self.expr_edit.toPlainText().strip()
    
    def get_active_fids(self):
        """Get the active feature IDs to update"""
        return set(self.active_fids)
