import dataclasses

from randovania.games.game import RandovaniaGame
from randovania.layout.base_configuration import BaseConfiguration
from randovania.layout.teleporters import TeleporterConfiguration


@dataclasses.dataclass(frozen=True)
class CorruptionConfiguration(BaseConfiguration):
    elevators: TeleporterConfiguration
    energy_per_tank: int = dataclasses.field(metadata={"min": 1, "max": 1000, "precision": 1})

    @classmethod
    def game_enum(cls) -> RandovaniaGame:
        return RandovaniaGame.PRIME3
