import collections
import dataclasses
import functools
import re
from typing import Dict, Optional, List

from PySide2 import QtCore, QtWidgets
from PySide2.QtCore import Qt
from PySide2.QtWidgets import QComboBox, QDialog, QGroupBox, QVBoxLayout

from randovania.game_description import default_database
from randovania.game_description.node import PickupNode
from randovania.game_description.resources.translator_gate import TranslatorGate
from randovania.game_description.resources.trick_resource_info import TrickResourceInfo
from randovania.game_description.world import World
from randovania.game_description.world_list import WorldList
from randovania.games.game import RandovaniaGame
from randovania.gui.dialog.trick_details_popup import TrickDetailsPopup
from randovania.gui.generated.logic_settings_window_ui import Ui_LogicSettingsWindow
from randovania.gui.lib import common_qt_lib, signal_handling
from randovania.gui.lib.area_list_helper import AreaListHelper
from randovania.gui.lib.common_qt_lib import set_combo_with_value
from randovania.gui.lib.trick_lib import difficulties_for_trick, used_tricks
from randovania.gui.lib.window_manager import WindowManager
from randovania.gui.preset_settings.echoes_beam_configuration_tab import PresetEchoesBeamConfiguration
from randovania.gui.preset_settings.echoes_goal_tab import PresetEchoesGoal
from randovania.gui.preset_settings.echoes_hints_tab import PresetEchoesHints
from randovania.gui.preset_settings.echoes_patches_tab import PresetEchoesPatches
from randovania.gui.preset_settings.echoes_translators_tab import PresetEchoesTranslators
from randovania.gui.preset_settings.elevators_tab import PresetElevators
from randovania.gui.preset_settings.item_pool_tab import PresetItemPool
from randovania.gui.preset_settings.preset_tab import PresetTab
from randovania.gui.preset_settings.prime_goal_tab import PresetPrimeGoal
from randovania.gui.preset_settings.prime_patches_tab import PresetPrimePatches
from randovania.gui.preset_settings.starting_area_tab import PresetStartingArea
from randovania.interface_common.options import Options
from randovania.interface_common.preset_editor import PresetEditor
from randovania.layout.available_locations import RandomizationMode
from randovania.layout.damage_strictness import LayoutDamageStrictness
from randovania.layout.echoes_configuration import EchoesConfiguration
from randovania.layout.preset import Preset
from randovania.layout.prime1.prime_configuration import PrimeConfiguration
from randovania.layout.trick_level import LayoutTrickLevel
from randovania.lib.enum_lib import iterate_enum


def _update_options_when_true(options: Options, field_name: str, new_value, checked: bool):
    if checked:
        with options:
            setattr(options, field_name, new_value)


def dark_world_flags(world: World):
    yield False
    if world.dark_name is not None:
        yield True


def _update_options_by_value(options: Options, combo: QComboBox, new_index: int):
    with options:
        setattr(options, combo.options_field_name, combo.currentData())


class LogicSettingsWindow(QDialog, Ui_LogicSettingsWindow, AreaListHelper):
    _extra_tabs: List[PresetTab]
    _combo_for_gate: Dict[TranslatorGate, QComboBox]
    _location_pool_for_node: Dict[PickupNode, QtWidgets.QCheckBox]
    _slider_for_trick: Dict[TrickResourceInfo, QtWidgets.QSlider]
    _editor: PresetEditor
    world_list: WorldList

    def __init__(self, window_manager: Optional[WindowManager], editor: PresetEditor):
        super().__init__()
        self.setupUi(self)
        common_qt_lib.set_default_window_icon(self)

        self._editor = editor
        self._window_manager = window_manager
        self.during_batch_check_update = False
        self._extra_tabs = []

        self.game_enum = editor.game
        self.game_description = default_database.game_description_for(self.game_enum)
        self.world_list = self.game_description.world_list
        self.resource_database = self.game_description.resource_database

        self._extra_tabs.append(PresetElevators(editor, self.game_description))
        self._extra_tabs.append(PresetStartingArea(editor, self.game_description))

        if self.game_enum == RandovaniaGame.PRIME1:
            self._extra_tabs.append(PresetPrimeGoal(editor))
            self._extra_tabs.append(PresetPrimePatches(editor))

        elif self.game_enum == RandovaniaGame.PRIME2:
            self._extra_tabs.append(PresetEchoesGoal(editor))
            self._extra_tabs.append(PresetEchoesHints(editor))
            self._extra_tabs.append(PresetEchoesTranslators(editor))
            self._extra_tabs.append(PresetEchoesBeamConfiguration(editor))
            self._extra_tabs.append(PresetEchoesPatches(editor))

        elif self.game_enum == RandovaniaGame.PRIME3:
            pass

        self._extra_tabs.append(PresetItemPool(editor))

        for extra_tab in self._extra_tabs:
            if extra_tab.uses_patches_tab:
                tab = self.patches_tab_widget
            else:
                tab = self.logic_tab_widget
            tab.addTab(extra_tab, extra_tab.tab_title)

        self.name_edit.textEdited.connect(self._edit_name)
        self.setup_trick_level_elements()
        self.setup_damage_elements()
        self.setup_location_pool_elements()

        # Alignment
        self.trick_level_layout.setAlignment(QtCore.Qt.AlignTop)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    # Options
    def on_preset_changed(self, preset: Preset):
        for extra_tab in self._extra_tabs:
            extra_tab.on_preset_changed(preset)

        # Variables
        config = preset.configuration

        # Title
        common_qt_lib.set_edit_if_different(self.name_edit, preset.name)

        # Trick Level
        trick_level_configuration = preset.configuration.trick_level
        self.trick_level_minimal_logic_check.setChecked(trick_level_configuration.minimal_logic)

        for trick, slider in self._slider_for_trick.items():
            assert self._slider_for_trick[trick] is slider
            slider.setValue(trick_level_configuration.level_for_trick(trick).as_number)
            slider.setEnabled(not trick_level_configuration.minimal_logic)

        # Damage
        set_combo_with_value(self.damage_strictness_combo, config.damage_strictness)
        self.energy_tank_capacity_spin_box.setValue(config.energy_per_tank)

        if self.game_enum == RandovaniaGame.PRIME2:
            self.dangerous_tank_check.setChecked(config.dangerous_energy_tank)
            self.safe_zone_logic_heal_check.setChecked(config.safe_zone.fully_heal)
            self.safe_zone_regen_spin.setValue(config.safe_zone.heal_per_second)
            self.varia_suit_spin_box.setValue(config.varia_suit_damage)
            self.dark_suit_spin_box.setValue(config.dark_suit_damage)

        elif self.game_enum == RandovaniaGame.PRIME1:
            self.progressive_damage_reduction_check.setChecked(config.progressive_damage_reduction)
            self.heated_damage_varia_check.setChecked(config.heat_protection_only_varia)
            self.heated_damage_spin.setValue(config.heat_damage)

        # Location Pool
        available_locations = config.available_locations
        set_combo_with_value(self.randomization_mode_combo, available_locations.randomization_mode)

        self.during_batch_check_update = True
        for node, check in self._location_pool_for_node.items():
            check.setChecked(node.pickup_index not in available_locations.excluded_indices)
            check.setEnabled(available_locations.randomization_mode == RandomizationMode.FULL or node.major_location)
        self.during_batch_check_update = False

    def _edit_name(self, value: str):
        with self._editor as editor:
            editor.name = value

    # Trick Level

    def _create_difficulty_details_row(self):
        row = 1

        trick_label = QtWidgets.QLabel(self.trick_level_scroll_contents)
        trick_label.setWordWrap(True)
        trick_label.setText("Difficulty Details")

        self.trick_difficulties_layout.addWidget(trick_label, row, 1, 1, -1)

        slider_layout = QtWidgets.QGridLayout()
        slider_layout.setHorizontalSpacing(0)
        for i in range(12):
            slider_layout.setColumnStretch(i, 1)
        #
        # if self._window_manager is not None:
        #     for i, trick_level in enumerate(LayoutTrickLevel):
        #         if trick_level not in {LayoutTrickLevel.NO_TRICKS, LayoutTrickLevel.MINIMAL_LOGIC}:
        #             tool_button = QtWidgets.QToolButton(self.trick_level_scroll_contents)
        #             tool_button.setText(trick_level.long_name)
        #             tool_button.clicked.connect(functools.partial(self._open_difficulty_details_popup, trick_level))
        #
        #             slider_layout.addWidget(tool_button, 1, 2 * i, 1, 2)

        self.trick_difficulties_layout.addLayout(slider_layout, row, 2, 1, 1)

    def setup_trick_level_elements(self):
        self.trick_level_minimal_logic_check.stateChanged.connect(self._on_trick_level_minimal_logic_check)

        self.trick_difficulties_layout = QtWidgets.QGridLayout()
        self._slider_for_trick = {}

        tricks_in_use = used_tricks(self.game_description)

        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)

        self._create_difficulty_details_row()

        row = 2
        for trick in sorted(self.resource_database.trick, key=lambda _trick: _trick.long_name):
            if trick not in tricks_in_use:
                continue

            if row > 1:
                self.trick_difficulties_layout.addItem(QtWidgets.QSpacerItem(20, 40,
                                                                             QtWidgets.QSizePolicy.Minimum,
                                                                             QtWidgets.QSizePolicy.Expanding))

            trick_label = QtWidgets.QLabel(self.trick_level_scroll_contents)
            trick_label.setSizePolicy(size_policy)
            trick_label.setWordWrap(True)
            trick_label.setFixedWidth(100)
            trick_label.setText(trick.long_name)

            self.trick_difficulties_layout.addWidget(trick_label, row, 1, 1, 1)

            slider_layout = QtWidgets.QGridLayout()
            slider_layout.setHorizontalSpacing(0)
            for i in range(12):
                slider_layout.setColumnStretch(i, 1)

            horizontal_slider = QtWidgets.QSlider(self.trick_level_scroll_contents)
            horizontal_slider.setMaximum(5)
            horizontal_slider.setPageStep(2)
            horizontal_slider.setOrientation(QtCore.Qt.Horizontal)
            horizontal_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
            horizontal_slider.setEnabled(False)
            horizontal_slider.valueChanged.connect(functools.partial(self._on_slide_trick_slider, trick))
            self._slider_for_trick[trick] = horizontal_slider
            slider_layout.addWidget(horizontal_slider, 0, 1, 1, 10)

            used_difficulties = difficulties_for_trick(self.game_description, trick)
            for i, trick_level in enumerate(iterate_enum(LayoutTrickLevel)):
                if trick_level == LayoutTrickLevel.DISABLED or trick_level in used_difficulties:
                    difficulty_label = QtWidgets.QLabel(self.trick_level_scroll_contents)
                    difficulty_label.setAlignment(QtCore.Qt.AlignHCenter)
                    difficulty_label.setText(trick_level.long_name)

                    slider_layout.addWidget(difficulty_label, 1, 2 * i, 1, 2)

            self.trick_difficulties_layout.addLayout(slider_layout, row, 2, 1, 1)

            if self._window_manager is not None:
                tool_button = QtWidgets.QToolButton(self.trick_level_scroll_contents)
                tool_button.setText("?")
                tool_button.clicked.connect(functools.partial(self._open_trick_details_popup, trick))
                self.trick_difficulties_layout.addWidget(tool_button, row, 3, 1, 1)

            row += 1

        self.trick_level_layout.addLayout(self.trick_difficulties_layout)

    def _on_slide_trick_slider(self, trick: TrickResourceInfo, value: int):
        if self._slider_for_trick[trick].isEnabled():
            with self._editor as options:
                options.set_configuration_field(
                    "trick_level",
                    options.configuration.trick_level.set_level_for_trick(
                        trick,
                        LayoutTrickLevel.from_number(value)
                    )
                )

    def _on_trick_level_minimal_logic_check(self, state: int):
        with self._editor as options:
            options.set_configuration_field(
                "trick_level",
                dataclasses.replace(options.configuration.trick_level,
                                    minimal_logic=bool(state))
            )

    def _exec_trick_details(self, popup: TrickDetailsPopup):
        self._trick_details_popup = popup
        self._trick_details_popup.setWindowModality(Qt.WindowModal)
        self._trick_details_popup.open()

    def _open_trick_details_popup(self, trick: TrickResourceInfo):
        self._exec_trick_details(TrickDetailsPopup(
            self,
            self._window_manager,
            self.game_description,
            trick,
            self._editor.configuration.trick_level.level_for_trick(trick),
        ))

    # Damage strictness
    def setup_damage_elements(self):
        self.damage_strictness_combo.setItemData(0, LayoutDamageStrictness.STRICT)
        self.damage_strictness_combo.setItemData(1, LayoutDamageStrictness.MEDIUM)
        self.damage_strictness_combo.setItemData(2, LayoutDamageStrictness.LENIENT)

        self.damage_strictness_combo.options_field_name = "layout_configuration_damage_strictness"
        self.damage_strictness_combo.currentIndexChanged.connect(functools.partial(_update_options_by_value,
                                                                                   self._editor,
                                                                                   self.damage_strictness_combo))

        def _persist_float(attribute_name: str):
            def persist(value: float):
                with self._editor as options:
                    options.set_configuration_field(attribute_name, value)

            return persist

        self.energy_tank_capacity_spin_box.valueChanged.connect(self._persist_tank_capacity)
        signal_handling.on_checked(self.dangerous_tank_check, self._persist_dangerous_tank)

        if self.game_enum == RandovaniaGame.PRIME2:
            config_fields = {
                field.name: field
                for field in dataclasses.fields(EchoesConfiguration)
            }
            self.varia_suit_spin_box.setMinimum(config_fields["varia_suit_damage"].metadata["min"])
            self.varia_suit_spin_box.setMaximum(config_fields["varia_suit_damage"].metadata["max"])
            self.dark_suit_spin_box.setMinimum(config_fields["dark_suit_damage"].metadata["min"])
            self.dark_suit_spin_box.setMaximum(config_fields["dark_suit_damage"].metadata["max"])

            signal_handling.on_checked(self.safe_zone_logic_heal_check, self._persist_safe_zone_logic_heal)
            self.safe_zone_regen_spin.valueChanged.connect(self._persist_safe_zone_regen)
            self.varia_suit_spin_box.valueChanged.connect(_persist_float("varia_suit_damage"))
            self.dark_suit_spin_box.valueChanged.connect(_persist_float("dark_suit_damage"))
        else:
            self.dark_aether_box.setVisible(False)
            self.safe_zone_box.setVisible(False)

        if self.game_enum == RandovaniaGame.PRIME1:
            config_fields = {
                field.name: field
                for field in dataclasses.fields(PrimeConfiguration)
            }
            self.heated_damage_spin.setMinimum(config_fields["heat_damage"].metadata["min"])
            self.heated_damage_spin.setMaximum(config_fields["heat_damage"].metadata["max"])

            signal_handling.on_checked(self.progressive_damage_reduction_check, self._persist_progressive_damage)
            signal_handling.on_checked(self.heated_damage_varia_check, self._persist_heat_protection_only_varia)
            self.heated_damage_spin.valueChanged.connect(_persist_float("heat_damage"))

        else:
            self.progressive_damage_reduction_check.setVisible(False)
            self.heated_damage_box.setVisible(False)

    def _persist_tank_capacity(self):
        with self._editor as editor:
            editor.set_configuration_field("energy_per_tank", int(self.energy_tank_capacity_spin_box.value()))

    def _persist_safe_zone_regen(self):
        with self._editor as editor:
            safe_zone = dataclasses.replace(
                editor.configuration.safe_zone,
                heal_per_second=self.safe_zone_regen_spin.value()
            )
            editor.set_configuration_field("safe_zone", safe_zone)

    def _persist_safe_zone_logic_heal(self, checked: bool):
        with self._editor as editor:
            safe_zone = dataclasses.replace(
                editor.configuration.safe_zone,
                fully_heal=checked
            )
            editor.set_configuration_field("safe_zone", safe_zone)

    def _persist_progressive_damage(self, checked: bool):
        with self._editor as editor:
            editor.set_configuration_field("progressive_damage_reduction", checked)

    def _persist_heat_protection_only_varia(self, checked: bool):
        with self._editor as editor:
            editor.set_configuration_field("heat_protection_only_varia", checked)

    def _persist_dangerous_tank(self, checked: bool):
        with self._editor as editor:
            editor.set_configuration_field("dangerous_energy_tank", checked)

    # Elevator

    # Location Pool
    def setup_location_pool_elements(self):
        self.randomization_mode_combo.setItemData(0, RandomizationMode.FULL)
        self.randomization_mode_combo.setItemData(1, RandomizationMode.MAJOR_MINOR_SPLIT)
        self.randomization_mode_combo.currentIndexChanged.connect(self._on_update_randomization_mode)

        vertical_layouts = [
            QtWidgets.QVBoxLayout(self.excluded_locations_area_contents),
            QtWidgets.QVBoxLayout(self.excluded_locations_area_contents),
        ]
        for layout in vertical_layouts:
            self.excluded_locations_area_layout.addLayout(layout)

        world_list = self.game_description.world_list
        self._location_pool_for_node = {}

        nodes_by_world = collections.defaultdict(list)
        node_names = {}
        pickup_match = re.compile(r"Pickup \(([^\)]+)\)")

        for world in world_list.worlds:
            for is_dark_world in dark_world_flags(world):
                for area in world.areas:
                    if area.in_dark_aether != is_dark_world:
                        continue
                    for node in area.nodes:
                        if isinstance(node, PickupNode):
                            nodes_by_world[world.correct_name(is_dark_world)].append(node)
                            match = pickup_match.match(node.name)
                            if match is not None:
                                node_name = match.group(1)
                            else:
                                node_name = node.name
                            node_names[node] = f"{world_list.nodes_to_area(node).name} ({node_name})"

        for i, world_name in enumerate(sorted(nodes_by_world.keys())):
            group_box = QGroupBox(self.excluded_locations_area_contents)
            group_box.setTitle(world_name)
            vertical_layout = QVBoxLayout(group_box)
            vertical_layout.setContentsMargins(8, 4, 8, 4)
            vertical_layout.setSpacing(2)
            group_box.vertical_layout = vertical_layout
            vertical_layouts[i % len(vertical_layouts)].addWidget(group_box)

            for node in sorted(nodes_by_world[world_name], key=node_names.get):
                check = QtWidgets.QCheckBox(group_box)
                check.setText(node_names[node])
                check.node = node
                check.stateChanged.connect(functools.partial(self._on_check_location, check))
                group_box.vertical_layout.addWidget(check)
                self._location_pool_for_node[node] = check

        for layout in vertical_layouts:
            layout.addSpacerItem(
                QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding))

    def _on_update_randomization_mode(self):
        with self._editor as editor:
            editor.available_locations = dataclasses.replace(
                editor.available_locations, randomization_mode=self.randomization_mode_combo.currentData())

    def _on_check_location(self, check: QtWidgets.QCheckBox, _):
        if self.during_batch_check_update:
            return
        with self._editor as editor:
            editor.available_locations = editor.available_locations.ensure_index(check.node.pickup_index,
                                                                                 not check.isChecked())
