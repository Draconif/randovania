from typing import Iterator, Dict, Tuple

from randovania.cython_graph.cgraph import OptimizedGameDescription
from randovania.game_description.node import Node, ResourceNode
from randovania.game_description.requirements import RequirementSet
from randovania.generator.generator_reach import GeneratorReach
from randovania.resolver.state import State


class NewGeneratorReach(GeneratorReach):
    def __deepcopy__(self, memodict):
        reach = NewGeneratorReach(self._optimized, self._state)
        return reach

    def __init__(self, game: OptimizedGameDescription, state: State):
        self._optimized = game
        self._state = state

    @classmethod
    def reach_from_state(cls,
                         game: OptimizedGameDescription,
                         initial_state: State,
                         ) -> "GeneratorReach":
        raise NotImplementedError()

    # Game related methods

    @property
    def game(self) -> OptimizedGameDescription:
        return self._optimized

    # ASDF

    @property
    def state(self) -> State:
        return self._state

    def advance_to(self, new_state: State,
                   is_safe: bool = False,
                   ) -> None:
        raise NotImplementedError()

    def act_on(self, node: ResourceNode) -> None:
        raise NotImplementedError()

    # Node stuff

    def is_reachable_node(self, node: Node) -> bool:
        raise NotImplementedError()

    @property
    def connected_nodes(self) -> Iterator[Node]:
        raise NotImplementedError()

    @property
    def nodes(self) -> Iterator[Node]:
        raise NotImplementedError()

    @property
    def safe_nodes(self) -> Iterator[Node]:
        raise NotImplementedError()

    def is_safe_node(self, node: Node) -> bool:
        raise NotImplementedError()

    def shortest_path_from(self, node: Node) -> Dict[Node, Tuple[Node, ...]]:
        raise NotImplementedError()

    def unreachable_nodes_with_requirements(self) -> Dict[Node, RequirementSet]:
        raise NotImplementedError()
