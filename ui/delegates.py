# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import QStyledItemDelegate, QStyle
from qgis.PyQt.QtGui import QColor, QBrush

class HighlightDelegate(QStyledItemDelegate):
    """Custom delegate that overrides Qt selection highlighting with our colors"""
    
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
    
    def paint(self, painter, option, index):
        """Override paint to use our custom highlight colors"""
        row = index.row()
        fid = self.dialog.get_fid_for_row(row)
        
        # Remove selection state so Qt doesn't draw its own blue selection overlay
        option.state = option.state & ~QStyle.State_Selected
        
        painter.save()
        if fid is not None and fid in self.dialog.highlighted_features:
            # Yellow for highlighted (selected in our system)
            painter.fillRect(option.rect, QColor(255, 255, 0))
        elif fid is not None:
            # Cyan for original selection
            painter.fillRect(option.rect, QColor(0, 255, 255))
        painter.restore()
            
        super().paint(painter, option, index)
