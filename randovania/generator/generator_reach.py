from typing import Iterator, Dict, Tuple

from randovania.cython_graph.cgraph import OptimizedGameDescription
from randovania.game_description.node import Node, ResourceNode
from randovania.game_description.requirements import RequirementSet
from randovania.resolver.state import State


class GeneratorReach:
    @classmethod
    def reach_from_state(cls,
                         game: OptimizedGameDescription,
                         initial_state: State,
                         ) -> "GeneratorReach":
        raise NotImplementedError()

    # Game related methods

    @property
    def game(self) -> OptimizedGameDescription:
        raise NotImplementedError()

    def victory_condition_satisfied(self):
        return self.game.victory_condition.satisfied(self.state.resources, self.state.energy)

    @property
    def all_nodes(self) -> Tuple[Node, ...]:
        return self.game.all_nodes

    # ASDF

    @property
    def state(self) -> State:
        raise NotImplementedError()

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
        """
        An iterator of all nodes there's an path from the reach's starting point. Similar to is_reachable_node
        :return:
        """
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



