import collections
from typing import List, Tuple, Dict, Set

import typing

from randovania.game_description.game_patches import GamePatches
from randovania.game_description.node import Node, ResourceNode
from randovania.game_description.requirements import ResourceRequirement, RequirementAnd, RequirementOr
from randovania.game_description.resources.resource_info import ResourceInfo
from randovania.game_description.resources.resource_type import ResourceType
from randovania.game_description.world_list import WorldList


def is_dmg(resource_req: ResourceRequirement) -> bool:
    return resource_req.resource.resource_type == ResourceType.DAMAGE


class NodeConnection:
    other: int
    requirements: Set[int]
    damage: Set[ResourceRequirement]

    def __init__(self, other, requirements, damage):
        self.other = other
        self.requirements = requirements
        self.damage = damage


class OptimizedWorldList:
    all_nodes: Tuple[Node, ...]
    requirements: List[ResourceRequirement]
    requirements_index: Dict[ResourceRequirement, int]
    adjacency: List[List[NodeConnection]]

    def __init__(self, all_nodes, requirements, requirements_index, adjacency):
        self.all_nodes = all_nodes
        self.requirements = requirements
        self.requirements_index = requirements_index
        self.adjacency = adjacency

    def requirement_for(self, source: Node, target: Node) -> RequirementOr:
        source_list = self.adjacency[source.index]
        target_index = target.index

        return RequirementOr([
            RequirementAnd([self.requirements[req] for req in connection.requirements] + list(connection.damage))
            for connection in source_list
            if connection.other == target_index
        ])

    def potential_nodes_from(self, source: Node):
        seen = set()
        for connection in self.adjacency[source.index]:
            target = self.all_nodes[connection.other]
            if target not in seen:
                seen.add(target)
                yield target, self.requirement_for(source, target)


def optimize_world(world_list: WorldList, patches: GamePatches,
                   dangerous_resources: typing.FrozenSet[ResourceInfo]) -> OptimizedWorldList:
    all_nodes = world_list.all_nodes

    resource_reqs = collections.defaultdict(int)
    adjacency: List[List[NodeConnection]] = []
    connections = {}

    for node in all_nodes:
        adjacency.append([])

        assert node.index == all_nodes.index(node)

        extra = [node.requirement_to_leave(patches, {})]
        if node.is_resource_node:
            node_resource = typing.cast(ResourceNode, node).resource()
            if node_resource in dangerous_resources:
                extra.append(ResourceRequirement(node_resource, 1, False))

        for target, requirement in world_list.potential_nodes_from(node, patches):
            req_set = RequirementAnd([requirement, *extra]).as_set
            connections[(node, target)] = req_set
            for resource_req in req_set.all_individual:
                if is_dmg(resource_req):
                    continue
                resource_reqs[resource_req] += 1

    requirements = sorted(resource_reqs.keys(), reverse=True, key=lambda t: (resource_reqs[t], t))
    requirements_index = {req: i for i, req in enumerate(requirements)}

    for (source, target), requirement in connections.items():
        source_list = adjacency[source.index]
        for alternative in requirement.alternatives:
            source_list.append(NodeConnection(
                target.index,
                {requirements_index[resource_req] for resource_req in alternative.items
                 if resource_req in requirements_index},
                {resource_req for resource_req in alternative.items if is_dmg(resource_req)},
            ))

    return OptimizedWorldList(all_nodes, requirements, requirements_index, adjacency)
