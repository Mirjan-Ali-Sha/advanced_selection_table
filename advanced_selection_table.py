# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QDockWidget, QToolBar
from qgis.core import QgsVectorLayer
from .ui.selection_widget import AdvancedSelectionDialog, AdvancedSelectionDock


class AdvancedSelectionTable:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr('&MAS Vector Processing')  # Shared menu with other MAS plugins
        self.toolbar = None
        self.selection_dialogs = {}
        self.selection_docks = {}
        
    def tr(self, message):
        return QCoreApplication.translate('AdvancedSelectionTable', message)
    
    def initGui(self):
        # Check if the MAS Vector Processing toolbar already exists; if not, create it
        self.toolbar = self.iface.mainWindow().findChild(QToolBar, 'MASVectorProcessingToolbar')
        if self.toolbar is None:
            self.toolbar = self.iface.addToolBar(self.tr('MAS Vector Processing'))
            self.toolbar.setObjectName('MASVectorProcessingToolbar')
        
        icon_path = os.path.join(self.plugin_dir, 'icons', 'icon.png')
        
        # Dock action - opens as docked panel (DEFAULT)
        self.action_dock = QAction(
            QIcon(icon_path), 
            self.tr(u'Advanced Selection Table (Dock)'), 
            self.iface.mainWindow()
        )
        self.action_dock.triggered.connect(self.run_dock)
        self.action_dock.setStatusTip(self.tr('Open advanced selection table as docked panel'))
        
        # Add to shared toolbar
        self.toolbar.addAction(self.action_dock)
        self.actions.append(self.action_dock)
        
        # Main action - opens as dialog (floating window) - Menu only
        self.action_dialog = QAction(
            QIcon(icon_path), 
            self.tr(u'Advanced Selection Table (Window)'), 
            self.iface.mainWindow()
        )
        self.action_dialog.triggered.connect(self.run_dialog)
        self.action_dialog.setStatusTip(self.tr('Open advanced selection table as floating window'))
        
        # Add both to MAS Vector Processing menu
        self.iface.addPluginToVectorMenu(self.menu, self.action_dock)
        self.iface.addPluginToVectorMenu(self.menu, self.action_dialog)
        self.actions.append(self.action_dialog)
    
    def unload(self):
        for action in self.actions:
            self.iface.removePluginVectorMenu(self.menu, action)
            # Remove from toolbar if present
            if self.toolbar:
                self.toolbar.removeAction(action)
        
        # Toolbar cleanup - QGIS will remove the toolbar if no actions remain
        if self.toolbar:
            self.toolbar = None
        
        # Close all dialogs
        for dialog in list(self.selection_dialogs.values()):
            if dialog:
                # Force cleanup of rubber bands explicitly
                if hasattr(dialog, 'selection_widget'):
                    dialog.selection_widget.cleanup_rubber_bands()
                dialog.close()
        
        # Close all docks
        for dock in list(self.selection_docks.values()):
            if dock:
                # Force cleanup of rubber bands explicitly because closeEvent might not fire
                # if the dock is removed/destroyed directly
                if hasattr(dock, 'selection_widget'):
                    dock.selection_widget.cleanup_rubber_bands()
                
                self.iface.removeDockWidget(dock)
                dock.deleteLater()
    
    def open_selection_dialog(self, layer):
        """Open as floating dialog window"""
        if not layer or not isinstance(layer, QgsVectorLayer):
            return
        
        layer_id = layer.id()
        
        # Check if dialog already exists
        if layer_id in self.selection_dialogs and self.selection_dialogs[layer_id]:
            self.selection_dialogs[layer_id].show()
            self.selection_dialogs[layer_id].raise_()
            return
        
        if layer.selectedFeatureCount() == 0:
            self.iface.messageBar().pushInfo('Selection', 'Select features first.')
            return
        
        dialog = AdvancedSelectionDialog(layer, self.iface, self.plugin_dir)
        self.selection_dialogs[layer_id] = dialog
        dialog.finished.connect(lambda: self.selection_dialogs.pop(layer_id, None))
        
        # Connect dock request signal - when user clicks "Dock" button in dialog
        dialog.dockRequested.connect(lambda: self.convert_to_dock(layer))
        
        dialog.show()
    
    def convert_to_dock(self, layer):
        """Convert floating dialog to docked panel"""
        layer_id = layer.id()
        
        # Close the dialog if it exists
        if layer_id in self.selection_dialogs:
            dialog = self.selection_dialogs.pop(layer_id, None)
            if dialog:
                dialog.close()
        
        # Open as dock
        self.open_selection_dock(layer)
    
    def open_selection_dock(self, layer):
        """Open as docked panel - tabified with existing attribute table docks"""
        if not layer or not isinstance(layer, QgsVectorLayer):
            return
        
        layer_id = layer.id()
        
        # Check if dock already exists
        if layer_id in self.selection_docks and self.selection_docks[layer_id]:
            self.selection_docks[layer_id].show()
            self.selection_docks[layer_id].raise_()
            return
        
        if layer.selectedFeatureCount() == 0:
            self.iface.messageBar().pushInfo('Selection', 'Select features first.')
            return
        
        dock = AdvancedSelectionDock(layer, self.iface, self.plugin_dir)
        self.selection_docks[layer_id] = dock
        dock.closed.connect(lambda: self.on_dock_closed(layer_id))
        dock.undockRequested.connect(lambda: self.convert_to_dialog(layer))
        
        # Add dock to QGIS interface
        self.iface.addDockWidget(Qt.BottomDockWidgetArea, dock)
        
        # Try to tabify with existing dock widgets in the bottom area
        # This makes it appear as a tab alongside the attribute table
        main_window = self.iface.mainWindow()
        existing_docks = main_window.findChildren(QDockWidget)
        
        for existing_dock in existing_docks:
            if existing_dock != dock and existing_dock.isVisible():
                # Check if the existing dock is in the bottom area
                area = main_window.dockWidgetArea(existing_dock)
                if area == Qt.BottomDockWidgetArea:
                    # Tabify our dock with the existing one
                    main_window.tabifyDockWidget(existing_dock, dock)
                    dock.raise_()  # Bring our dock tab to front
                    break
        
        dock.show()
    
    def convert_to_dialog(self, layer):
        """Convert docked panel back to floating dialog"""
        layer_id = layer.id()
        
        # Close the dock if it exists
        if layer_id in self.selection_docks:
            dock = self.selection_docks.pop(layer_id, None)
            if dock:
                # CRITICAL: Cleanup rubber bands before removing dock
                if hasattr(dock, 'selection_widget'):
                    dock.selection_widget.cleanup_rubber_bands()
                self.iface.removeDockWidget(dock)
                dock.deleteLater()
        
        # Open as dialog
        self.open_selection_dialog(layer)
    
    def on_dock_closed(self, layer_id):
        """Handle dock widget closed"""
        if layer_id in self.selection_docks:
            dock = self.selection_docks.pop(layer_id, None)
            if dock:
                self.iface.removeDockWidget(dock)
                dock.deleteLater()
    
    def run_dialog(self):
        """Open as floating dialog"""
        layer = self.iface.activeLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning('Selection', 'Select a vector layer.')
            return
        self.open_selection_dialog(layer)
    
    def run_dock(self):
        """Open as docked panel"""
        layer = self.iface.activeLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            self.iface.messageBar().pushWarning('Selection', 'Select a vector layer.')
            return
        self.open_selection_dock(layer)
