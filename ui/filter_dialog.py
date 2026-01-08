# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSplitter, QWidget, QGroupBox, 
    QComboBox, QPushButton, QLineEdit, QListWidget, QListWidgetItem, 
    QDialogButtonBox, QTextEdit, QApplication
)
from qgis.core import QgsFeatureRequest, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils

class SelectionFilterDialog(QDialog):
    """
    Advanced expression builder with proper value extraction, 
    logical operators, condition management, and expanded expression editor.
    """
    
    def __init__(self, layer, selected_fids, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.selected_fids = selected_fids
        self.conditions = []  # List of (logic, expression) tuples
        self.value_cache = {}
        
        self.setWindowTitle('Advanced Filter Builder')
        self.setMinimumSize(800, 650)
        self.setup_ui()
        self.cache_all_field_values()
        self.load_fields()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)
        self.setLayout(layout)
        
        # Header
        header = QLabel(
            f'<b style="color:#006064;">🔍 Filter within {len(self.selected_fids)} selected features</b>'
        )
        header.setStyleSheet("padding: 8px; background: linear-gradient(to right, #e0f7fa, #b2ebf2); border-radius: 4px;")
        layout.addWidget(header)
        
        # Main content - horizontal splitter
        main_splitter = QSplitter(Qt.Horizontal)
        
        # === LEFT PANEL: Field + Operator ===
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_widget.setLayout(left_layout)
        
        # Field group
        field_group = QGroupBox("📋 Field")
        field_layout = QVBoxLayout()
        self.field_combo = QComboBox()
        self.field_combo.currentIndexChanged.connect(self.on_field_changed)
        field_layout.addWidget(self.field_combo)
        self.field_type_label = QLabel()
        self.field_type_label.setStyleSheet("color: #666; font-size: 10px;")
        field_layout.addWidget(self.field_type_label)
        field_group.setLayout(field_layout)
        left_layout.addWidget(field_group)
        
        # Operator group
        op_group = QGroupBox("⚙️ Operator")
        op_layout = QVBoxLayout()
        self.op_combo = QComboBox()
        self.op_combo.addItems([
            '= (equals)', '!= (not equals)', 
            '> (greater)', '< (less)', '>= (greater/equal)', '<= (less/equal)',
            'LIKE (contains)', 'NOT LIKE', 
            'IN (any of)', 'NOT IN',
            'IS NULL', 'IS NOT NULL', 'BETWEEN'
        ])
        self.op_combo.currentIndexChanged.connect(self.on_operator_changed)
        op_layout.addWidget(self.op_combo)
        op_group.setLayout(op_layout)
        left_layout.addWidget(op_group)
        
        # Logical Operators group
        logic_group = QGroupBox("🔗 Logical Operators")
        logic_layout = QVBoxLayout()
        
        # Operator buttons
        and_btn = QPushButton("AND")
        and_btn.setToolTip("Insert AND operator")
        and_btn.clicked.connect(lambda: self.insert_logic_operator("AND"))
        or_btn = QPushButton("OR")
        or_btn.setToolTip("Insert OR operator")
        or_btn.clicked.connect(lambda: self.insert_logic_operator("OR"))
        not_btn = QPushButton("NOT")
        not_btn.setToolTip("Insert NOT operator")
        not_btn.clicked.connect(lambda: self.insert_logic_operator("NOT"))
        
        logic_row1 = QHBoxLayout()
        logic_row1.addWidget(and_btn)
        logic_row1.addWidget(or_btn)
        logic_row1.addWidget(not_btn)
        logic_layout.addLayout(logic_row1)
        
        # Parentheses
        open_paren = QPushButton("(")
        open_paren.clicked.connect(lambda: self.insert_logic_operator("("))
        close_paren = QPushButton(")")
        close_paren.clicked.connect(lambda: self.insert_logic_operator(")"))
        
        logic_row2 = QHBoxLayout()
        logic_row2.addWidget(open_paren)
        logic_row2.addWidget(close_paren)
        logic_layout.addLayout(logic_row2)
        
        logic_group.setLayout(logic_layout)
        left_layout.addWidget(logic_group)
        
        left_layout.addStretch()
        main_splitter.addWidget(left_widget)
        
        # === RIGHT PANEL: Values ===
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_widget.setLayout(right_layout)
        
        # Value group
        value_group = QGroupBox("📊 Values (from selection only)")
        value_layout = QVBoxLayout()
        
        # Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔎"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search values...")
        self.search_box.textChanged.connect(self.filter_values)
        search_layout.addWidget(self.search_box)
        value_layout.addLayout(search_layout)
        
        # Value list
        self.value_list = QListWidget()
        self.value_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.value_list.itemDoubleClicked.connect(lambda: self.add_condition_with_logic('AND'))
        value_layout.addWidget(self.value_list)
        
        # Stats
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #666; font-size: 10px;")
        value_layout.addWidget(self.stats_label)
        
        # Manual input
        self.manual_value = QLineEdit()
        self.manual_value.setPlaceholderText("Or enter custom value...")
        value_layout.addWidget(self.manual_value)
        
        value_group.setLayout(value_layout)
        right_layout.addWidget(value_group)
        main_splitter.addWidget(right_widget)
        
        main_splitter.setSizes([280, 450])
        layout.addWidget(main_splitter)
        
        # === CONDITION BUILDER BUTTONS ===
        btn_layout = QHBoxLayout()
        
        add_and_btn = QPushButton("➕ Add with AND")
        add_and_btn.setStyleSheet("background-color: #c8e6c9; font-weight: bold; padding: 6px;")
        add_and_btn.clicked.connect(lambda: self.add_condition_with_logic('AND'))
        btn_layout.addWidget(add_and_btn)
        
        add_or_btn = QPushButton("➕ Add with OR")
        add_or_btn.setStyleSheet("background-color: #ffe0b2; font-weight: bold; padding: 6px;")
        add_or_btn.clicked.connect(lambda: self.add_condition_with_logic('OR'))
        btn_layout.addWidget(add_or_btn)
        
        add_simple_btn = QPushButton("➕ Add (no logic)")
        add_simple_btn.clicked.connect(lambda: self.add_condition_with_logic(None))
        btn_layout.addWidget(add_simple_btn)
        
        layout.addLayout(btn_layout)
        
        # === CONDITIONS LIST ===
        cond_group = QGroupBox("📝 Conditions (click to select, then remove)")
        cond_layout = QVBoxLayout()
        
        self.conditions_list = QListWidget()
        self.conditions_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.conditions_list.setMinimumHeight(80)
        self.conditions_list.setStyleSheet("font-family: monospace; font-size: 11px;")
        cond_layout.addWidget(self.conditions_list)
        
        # Remove selected conditions button
        remove_layout = QHBoxLayout()
        remove_btn = QPushButton("🗑️ Remove Selected")
        remove_btn.clicked.connect(self.remove_selected_conditions)
        remove_layout.addWidget(remove_btn)
        
        clear_btn = QPushButton("🗑️ Clear All")
        clear_btn.clicked.connect(self.clear_conditions)
        remove_layout.addWidget(clear_btn)
        
        remove_layout.addStretch()
        cond_layout.addLayout(remove_layout)
        
        cond_group.setLayout(cond_layout)
        layout.addWidget(cond_group)
        
        # === EXPRESSION EDITOR (EXPANDED) ===
        expr_group = QGroupBox("📄 Expression (editable - you can type directly)")
        expr_layout = QVBoxLayout()
        
        # Use QTextEdit for multi-line
        self.expr_edit = QTextEdit()
        self.expr_edit.setMinimumHeight(80)
        self.expr_edit.setStyleSheet(
            "font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; "
            "padding: 8px; background-color: #fffde7; border: 1px solid #ddd;"
        )
        self.expr_edit.setPlaceholderText("Expression will appear here...\nYou can also edit directly.")
        expr_layout.addWidget(self.expr_edit)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        test_btn = QPushButton("🧪 Test Expression")
        test_btn.clicked.connect(self.test_expression)
        action_layout.addWidget(test_btn)
        
        copy_btn = QPushButton("📋 Copy")
        copy_btn.clicked.connect(self.copy_expression)
        action_layout.addWidget(copy_btn)
        
        build_btn = QPushButton("🔨 Rebuild from Conditions")
        build_btn.clicked.connect(self.rebuild_expression)
        action_layout.addWidget(build_btn)
        
        action_layout.addStretch()
        
        self.match_label = QLabel()
        self.match_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        action_layout.addWidget(self.match_label)
        
        expr_layout.addLayout(action_layout)
        expr_group.setLayout(expr_layout)
        layout.addWidget(expr_group)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.Ok).setText("Apply Filter")
        button_box.button(QDialogButtonBox.Ok).setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 8px 20px;"
        )
        layout.addWidget(button_box)
    
    def cache_all_field_values(self):
        """Cache all field values from selected features"""
        request = QgsFeatureRequest().setFilterFids(list(self.selected_fids))
        
        for field in self.layer.fields():
            self.value_cache[field.name()] = {}
        
        for feature in self.layer.getFeatures(request):
            for field in self.layer.fields():
                value = feature.attribute(field.name())
                if value is not None:
                    str_val = str(value)
                    self.value_cache[field.name()][str_val] = \
                        self.value_cache[field.name()].get(str_val, 0) + 1
    
    def load_fields(self):
        """Load field names"""
        self.field_combo.clear()
        for field in self.layer.fields():
            self.field_combo.addItem(field.name(), field.name())
        if self.field_combo.count() > 0:
            self.on_field_changed(0)
    
    def on_field_changed(self, index):
        """Handle field selection change"""
        if index < 0:
            return
        field_name = self.field_combo.currentData() or self.field_combo.currentText()
        
        for field in self.layer.fields():
            if field.name() == field_name:
                self.field_type_label.setText(f"Type: {field.typeName()}")
                break
        
        self.populate_value_list(field_name)
    
    def populate_value_list(self, field_name, filter_text=''):
        """Populate value list - store clean values"""
        self.value_list.clear()
        
        if field_name not in self.value_cache:
            return
        
        values = self.value_cache[field_name]
        total = sum(values.values())
        shown = 0
        
        for value in sorted(values.keys()):
            if filter_text and filter_text.lower() not in value.lower():
                continue
            count = values[value]
            # Display with count, store clean value
            item = QListWidgetItem(f"{value}  ({count})")
            item.setData(Qt.UserRole, value)  # IMPORTANT: Store CLEAN value
            self.value_list.addItem(item)
            shown += 1
        
        self.stats_label.setText(f"{shown} of {len(values)} values ({total} features)")
    
    def filter_values(self, text):
        """Filter values by search text"""
        field_name = self.field_combo.currentData() or self.field_combo.currentText()
        self.populate_value_list(field_name, text)
    
    def on_operator_changed(self, index):
        """Update UI for operator"""
        op_text = self.op_combo.currentText()
        if 'NULL' in op_text:
            self.value_list.setEnabled(False)
            self.manual_value.setEnabled(False)
        else:
            self.value_list.setEnabled(True)
            self.manual_value.setEnabled(True)
    
    def get_operator_symbol(self):
        """Extract operator from combo text"""
        text = self.op_combo.currentText()
        if 'IS NOT NULL' in text: return 'IS NOT NULL'
        if 'IS NULL' in text: return 'IS NULL'
        if 'NOT LIKE' in text: return 'NOT LIKE'
        if 'LIKE' in text: return 'LIKE'
        if 'NOT IN' in text: return 'NOT IN'
        if 'BETWEEN' in text: return 'BETWEEN'
        if 'IN' in text: return 'IN'
        if '!=' in text: return '!='
        if '>=' in text: return '>='
        if '<=' in text: return '<='
        if '>' in text: return '>'
        if '<' in text: return '<'
        if '=' in text: return '='
        return '='
    
    def build_single_condition(self):
        """Build ONE condition from current UI state"""
        field = self.field_combo.currentData() or self.field_combo.currentText()
        op = self.get_operator_symbol()
        
        # NULL operators don't need value
        if op in ('IS NULL', 'IS NOT NULL'):
            return f'"{field}" {op}'
        
        # Get values - IMPORTANT: use UserRole data, not text
        selected_items = self.value_list.selectedItems()
        manual = self.manual_value.text().strip()
        
        if manual:
            values = [manual]
        elif selected_items:
            values = [item.data(Qt.UserRole) for item in selected_items]
        else:
            return None
        
        # BETWEEN
        if op == 'BETWEEN':
            if len(values) >= 2:
                return f'"{field}" BETWEEN {values[0]} AND {values[1]}'
            elif ' AND ' in values[0].upper():
                return f'"{field}" BETWEEN {values[0]}'
            return None
        
        # IN / NOT IN or multiple values
        if op in ('IN', 'NOT IN') or len(values) > 1:
            quoted = []
            for v in values:
                try:
                    float(v)
                    quoted.append(str(v))
                except ValueError:
                    quoted.append(f"'{v}'")
            actual_op = 'NOT IN' if op == 'NOT IN' else 'IN'
            return f'"{field}" {actual_op} ({", ".join(quoted)})'
        
        # Single value
        value = values[0]
        try:
            float(value)
            is_numeric = True
        except ValueError:
            is_numeric = False
        
        if op in ('LIKE', 'NOT LIKE'):
            return f'"{field}" {op} \'%{value}%\''
        elif is_numeric:
            return f'"{field}" {op} {value}'
        else:
            return f'"{field}" {op} \'{value}\''
    
    def add_condition_with_logic(self, logic):
        """Add condition with specified logic (AND/OR/None)"""
        condition = self.build_single_condition()
        if not condition:
            return
        
        self.conditions.append((logic, condition))
        self.update_conditions_display()
        self.rebuild_expression()
    
    def insert_logic_operator(self, op):
        """Insert logic operator at cursor in expression editor"""
        cursor = self.expr_edit.textCursor()
        cursor.insertText(f" {op} ")
    
    def remove_selected_conditions(self):
        """Remove selected conditions from list"""
        selected_rows = sorted([self.conditions_list.row(item) for item in self.conditions_list.selectedItems()], reverse=True)
        for row in selected_rows:
            if row < len(self.conditions):
                del self.conditions[row]
        self.update_conditions_display()
        self.rebuild_expression()
    
    def clear_conditions(self):
        """Clear all conditions"""
        self.conditions.clear()
        self.conditions_list.clear()
        self.expr_edit.clear()
        self.match_label.clear()
    
    def update_conditions_display(self):
        """Update conditions list widget"""
        self.conditions_list.clear()
        for i, (logic, expr) in enumerate(self.conditions):
            if logic and i > 0:
                self.conditions_list.addItem(f"{logic} {expr}")
            else:
                self.conditions_list.addItem(expr)
    
    def rebuild_expression(self):
        """Rebuild expression from conditions list"""
        if not self.conditions:
            self.expr_edit.clear()
            return
        
        parts = []
        for i, (logic, expr) in enumerate(self.conditions):
            if logic and i > 0:
                parts.append(logic)
            parts.append(expr)
        
        self.expr_edit.setPlainText(' '.join(parts))
    
    def test_expression(self):
        """Test expression and show match count - manually evaluate on each feature"""
        expr_text = self.expr_edit.toPlainText().strip()
        if not expr_text:
            self.match_label.setText("No expression")
            self.match_label.setStyleSheet("color: #666;")
            return
        
        try:
            # Create and prepare expression
            expr = QgsExpression(expr_text)
            if expr.hasParserError():
                self.match_label.setText(f"❌ Parse error: {expr.parserErrorString()[:30]}")
                self.match_label.setStyleSheet("color: #c62828;")
                return
            
            # Create context
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(self.layer))
            
            # Get features from selection and evaluate manually
            request = QgsFeatureRequest().setFilterFids(list(self.selected_fids))
            count = 0
            for feature in self.layer.getFeatures(request):
                context.setFeature(feature)
                result = expr.evaluate(context)
                if result:
                    count += 1
            
            self.match_label.setText(f"✅ {count} matches out of {len(self.selected_fids)}")
            self.match_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        except Exception as e:
            self.match_label.setText(f"❌ Error: {str(e)[:30]}")
            self.match_label.setStyleSheet("color: #c62828;")
    
    def copy_expression(self):
        """Copy expression to clipboard"""
        QApplication.clipboard().setText(self.expr_edit.toPlainText())
    
    def get_expression(self):
        """Return the expression"""
        return self.expr_edit.toPlainText().strip()
