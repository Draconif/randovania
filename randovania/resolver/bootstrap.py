import copy
import dataclasses
from typing import Tuple

from randovania.game_description import default_database
from randovania.game_description.game_description import GameDescription
from randovania.game_description.game_patches import GamePatches
from randovania.game_description.node import PlayerShipNode
from randovania.game_description.resources.damage_resource_info import DamageReduction
from randovania.game_description.resources.resource_database import ResourceDatabase
from randovania.game_description.resources.resource_info import CurrentResources, \
    add_resource_gain_to_current_resources
from randovania.game_description.resources.resource_type import ResourceType
from randovania.games.game import RandovaniaGame
from randovania.layout.major_items_configuration import MajorItemsConfiguration
from randovania.layout.preset import AnyGameConfiguration
from randovania.layout.trick_level import LayoutTrickLevel
from randovania.layout.trick_level_configuration import TrickLevelConfiguration
from randovania.resolver.state import State, StateGameData

_items_to_not_add_in_minimal_logic = {
    # Dark Visor
    10,

    # Dark Suit, Light Suit
    13,
    14,

    # Grapple, Screw Attack
    23,
    27,

    # Dark Agon Temple Keys
    32, 33, 34,

    # Dark Torvus Temple Keys
    35, 36, 37,

    # Sky Temple Keys
    29, 30, 31, 101, 102, 103, 104, 105, 106
}

_minimal_logic_custom_item_count = {
    # Energy Tank
    42: 14,
    # Power Bomb
    43: 10,
    # Missile
    44: 100,
    # Dark Ammo
    45: 100,
    # Light Ammo
    46: 100
}

_events_for_vanilla_item_loss_from_ship = {
    2,
    4,
    71,
    78,
}


def trick_resources_for_configuration(configuration: TrickLevelConfiguration,
                                      resource_database: ResourceDatabase,
                                      ) -> CurrentResources:
    """
    :param configuration:
    :param resource_database:
    :return:
    """

    static_resources = {}

    for trick in resource_database.trick:
        if configuration.minimal_logic:
            level = LayoutTrickLevel.maximum()
        else:
            level = configuration.level_for_trick(trick)
        static_resources[trick] = level.as_number

    return static_resources


def _add_minimal_logic_initial_resources(resources: CurrentResources,
                                         resource_database: ResourceDatabase,
                                         major_items: MajorItemsConfiguration,
                                         ) -> None:
    # TODO: this function assumes we're talking about Echoes
    for event in resource_database.event:
        # Ignoring these events:
        # Dark Samus 3 and 4 (93), otherwise we're done automatically (TODO: get this from database)
        # Chykka (28), otherwise we can't collect Dark Visor
        if event.index not in {28, 93}:
            resources[event] = 1

    item_db = default_database.item_database_for_game(RandovaniaGame.PRIME2)

    items_to_skip = copy.copy(_items_to_not_add_in_minimal_logic)
    if major_items.items_state[item_db.major_items["Progressive Grapple"]].num_shuffled_pickups == 0:
        items_to_skip.remove(23)
    if major_items.items_state[item_db.major_items["Progressive Suit"]].num_shuffled_pickups == 0:
        items_to_skip.remove(13)

    for item in resource_database.item:
        if item.index not in items_to_skip:
            resources[item] = _minimal_logic_custom_item_count.get(item.index, 1)


def calculate_starting_state(game: GameDescription, patches: GamePatches, energy_per_tank: int) -> "State":
    starting_node = game.world_list.resolve_teleporter_connection(patches.starting_location)
    initial_resources = copy.copy(patches.starting_items)

    if isinstance(starting_node, PlayerShipNode):
        add_resource_gain_to_current_resources(
            starting_node.resource_gain_on_collect(patches, initial_resources, game.world_list.all_nodes,
                                                   game.resource_database),
            initial_resources,
        )

    initial_game_state = game.initial_states.get("Default")
    if initial_game_state is not None:
        add_resource_gain_to_current_resources(initial_game_state, initial_resources)

    starting_state = State(
        initial_resources,
        (),
        99 + (100 * initial_resources.get(game.resource_database.energy_tank, 0)),
        starting_node,
        patches,
        None,
        StateGameData(
            game.resource_database,
            game.world_list,
            energy_per_tank,
        )
    )

    # Being present with value 0 is troublesome since this dict is used for a simplify_requirements later on
    keys_to_remove = [resource for resource, quantity in initial_resources.items() if quantity == 0]
    for resource in keys_to_remove:
        del initial_resources[resource]

    return starting_state


def version_resources_for_game(resource_database: ResourceDatabase) -> CurrentResources:
    # All version differences are patched out from the game
    return {
        resource: 1 if resource.long_name == "NTSC" else 0
        for resource in resource_database.version
    }


def misc_resources_for_configuration(configuration: AnyGameConfiguration,
                                     resource_database: ResourceDatabase) -> CurrentResources:
    enabled_resources = {}
    if configuration.game == RandovaniaGame.PRIME2:
        enabled_resources = {
            # Allow Vanilla X
            19, 20, 21, 22, 23, 24, 25
        }
        if configuration.elevators.is_vanilla:
            # Vanilla Great Temple Emerald Translator Gate
            enabled_resources.add(18)

    return {
        resource: 1 if resource.index in enabled_resources else 0
        for resource in resource_database.misc
    }


def prime1_progressive_damage_reduction(db: ResourceDatabase, current_resources: CurrentResources):
    num_suits = sum(current_resources.get(db.get_item_by_name(suit), 0)
                    for suit in ["Varia Suit", "Gravity Suit", "Phazon Suit"])
    if num_suits >= 3:
        return 0.5
    elif num_suits == 2:
        return 0.8
    elif num_suits == 1:
        return 0.9
    else:
        return 1


def prime1_absolute_damage_reduction(db: ResourceDatabase, current_resources: CurrentResources):
    if current_resources.get(db.get_item_by_name("Phazon Suit"), 0) > 0:
        return 0.5
    elif current_resources.get(db.get_item_by_name("Gravity Suit"), 0) > 0:
        return 0.8
    elif current_resources.get(db.get_item_by_name("Varia Suit"), 0) > 0:
        return 0.9
    else:
        return 1


def patch_resource_database(db: ResourceDatabase, configuration: AnyGameConfiguration) -> ResourceDatabase:
    base_damage_reduction = db.base_damage_reduction
    damage_reductions = copy.copy(db.damage_reductions)

    if configuration.game == RandovaniaGame.PRIME1:
        reductions = [
            DamageReduction(None, configuration.heat_damage / 10.0),
        ]
        suits = [db.get_item_by_name("Varia Suit")]
        if not configuration.heat_protection_only_varia:
            suits.extend([db.get_item_by_name("Gravity Suit"), db.get_item_by_name("Phazon Suit")])

        reductions.extend([
            DamageReduction(suit, 0)
            for suit in suits
        ])
        damage_reductions[db.get_by_type_and_index(ResourceType.DAMAGE, 5)] = reductions
        if configuration.progressive_damage_reduction:
            base_damage_reduction = prime1_progressive_damage_reduction
        else:
            base_damage_reduction = prime1_absolute_damage_reduction

    elif configuration.game == RandovaniaGame.PRIME2:
        damage_reductions[db.get_by_type_and_index(ResourceType.DAMAGE, 2)] = [
            DamageReduction(None, configuration.varia_suit_damage / 6.0),
            DamageReduction(db.get_item_by_name("Dark Suit"), configuration.dark_suit_damage / 6.0),
            DamageReduction(db.get_item_by_name("Light Suit"), 0.0),
        ]

    return dataclasses.replace(db, damage_reductions=damage_reductions, base_damage_reduction=base_damage_reduction)


def logic_bootstrap(configuration: AnyGameConfiguration,
                    game: GameDescription,
                    patches: GamePatches,
                    ) -> Tuple[GameDescription, State]:
    """
    Core code for starting a new Logic/State.
    :param configuration:
    :param game:
    :param patches:
    :return:
    """
    game = copy.deepcopy(game)
    game.resource_database = patch_resource_database(game.resource_database, configuration)
    starting_state = calculate_starting_state(game, patches, configuration.energy_per_tank)

    if configuration.trick_level.minimal_logic:
        _add_minimal_logic_initial_resources(starting_state.resources,
                                             game.resource_database,
                                             configuration.major_items_configuration)

    static_resources = trick_resources_for_configuration(configuration.trick_level,
                                                         game.resource_database)
    static_resources.update(version_resources_for_game(game.resource_database))
    static_resources.update(misc_resources_for_configuration(configuration, game.resource_database))

    for resource, quantity in static_resources.items():
        starting_state.resources[resource] = quantity

    game.patch_requirements(starting_state.resources, configuration.damage_strictness.value)

    return game, starting_state
