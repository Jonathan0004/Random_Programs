import math
import random
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pygame


# --- Core constants ---
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480
TILE_SIZE = 24
MAP_WIDTH = 20
MAP_HEIGHT = 15
FPS = 60


Color = pygame.Color
COLORS: Dict[str, Color] = {
    "grass": Color(72, 168, 72),
    "road": Color(180, 147, 93),
    "tree": Color(30, 110, 30),
    "water": Color(60, 140, 200),
    "sand": Color(218, 195, 148),
    "rock": Color(100, 100, 100),
    "roof": Color(150, 55, 55),
    "wall": Color(194, 172, 146),
    "floor": Color(235, 221, 200),
    "bridge": Color(139, 108, 66),
    "flower": Color(200, 70, 130),
    "shadow": Color(0, 0, 0, 90),
    "ui": Color(16, 16, 16),
    "ui_text": Color(235, 235, 235),
}


@dataclass
class Entity:
    x: float
    y: float
    speed: float
    width: int = 18
    height: int = 18
    facing: str = "down"

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)


@dataclass
class NPC(Entity):
    name: str = ""
    lines: List[str] = field(default_factory=list)
    give_item: Optional[str] = None
    required_item: Optional[str] = None
    required_stage: int = 0
    set_stage: Optional[int] = None
    once: bool = False
    has_spoken: bool = False

    def interact(self, game: "Game") -> str:
        if self.required_stage and game.story_stage < self.required_stage:
            return "They look at you, waiting for you to prove yourself first."
        if self.required_item and self.required_item not in game.inventory:
            return f"{self.name}: Come back when you have {self.required_item}."
        if self.once and self.has_spoken:
            return f"{self.name}: Stay safe out there, hero."
        self.has_spoken = True
        message = "\n".join(self.lines)
        if self.give_item and self.give_item not in game.inventory:
            game.inventory.add(self.give_item)
            message += f"\nYou received {self.give_item}!"
        if self.set_stage is not None and game.story_stage < self.set_stage:
            game.story_stage = self.set_stage
            message += f"\nStory progressed to stage {game.story_stage}."
        return message


@dataclass
class Enemy(Entity):
    patrol_range: int = 32
    base_x: float = 0
    base_y: float = 0
    alive: bool = True

    def update(self, dt: float, obstacles: List[pygame.Rect]):
        if not self.alive:
            return
        # Simple floating patrol
        angle = pygame.time.get_ticks() / 600.0
        self.x = self.base_x + math.sin(angle) * self.patrol_range
        self.y = self.base_y + math.cos(angle) * self.patrol_range
        self.rect.clamp_ip(pygame.Rect(0, 0, MAP_WIDTH * TILE_SIZE, MAP_HEIGHT * TILE_SIZE))
        for block in obstacles:
            if self.rect.colliderect(block):
                self.x = self.base_x
                self.y = self.base_y
                break


@dataclass
class Portal:
    area: str
    spawn: Tuple[int, int]
    message: str = ""


@dataclass
class Area:
    key: str
    name: str
    biome: str
    layout: List[str]
    npcs: List[NPC] = field(default_factory=list)
    enemies: List[Enemy] = field(default_factory=list)
    portals: Dict[Tuple[int, int], Portal] = field(default_factory=dict)
    edge_locks: Dict[str, Tuple[str, str]] = field(default_factory=dict)  # dir -> (item, message)

    def obstacles(self) -> List[pygame.Rect]:
        blocked = []
        for y, row in enumerate(self.layout):
            for x, tile in enumerate(row):
                if tile in {"T", "B", "M", "W"}:
                    blocked.append(pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        return blocked


class MapManager:
    def __init__(self, areas: Dict[str, Area]):
        self.areas = areas
        self.current_key = "1,1"
        self.transition: Optional[Dict] = None

    def set_current(self, key: str):
        if key in self.areas:
            self.current_key = key

    def get_area(self, key: Optional[str] = None) -> Area:
        return self.areas[key or self.current_key]

    def neighbor(self, direction: str, current_key: Optional[str] = None) -> Optional[str]:
        key = current_key or self.current_key
        if "," not in key:
            return None
        x, y = map(int, key.split(","))
        if direction == "left":
            x -= 1
        elif direction == "right":
            x += 1
        elif direction == "up":
            y -= 1
        elif direction == "down":
            y += 1
        neighbor_key = f"{x},{y}"
        return neighbor_key if neighbor_key in self.areas else None


class Player(Entity):
    def __init__(self, x: float, y: float):
        super().__init__(x, y, speed=110, width=18, height=18)
        self.attack_timer = 0.0
        self.attack_cooldown = 0.35

    def attack_rect(self) -> pygame.Rect:
        length = 18
        if self.facing == "up":
            return pygame.Rect(self.rect.centerx - 6, self.rect.top - length, 12, length)
        if self.facing == "down":
            return pygame.Rect(self.rect.centerx - 6, self.rect.bottom, 12, length)
        if self.facing == "left":
            return pygame.Rect(self.rect.left - length, self.rect.centery - 6, length, 12)
        return pygame.Rect(self.rect.right, self.rect.centery - 6, length, 12)

    def update(self, dt: float, area: Area, game: "Game"):
        keys = pygame.key.get_pressed()
        vx = vy = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            vx = -1
            self.facing = "left"
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            vx = 1
            self.facing = "right"
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            vy = -1
            self.facing = "up" if vx == 0 else self.facing
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            vy = 1
            self.facing = "down" if vx == 0 else self.facing

        if self.attack_timer > 0:
            self.attack_timer -= dt

        if game.transitioning:
            return

        # Movement and collisions
        norm = math.hypot(vx, vy)
        if norm:
            vx /= norm
            vy /= norm
        self.x += vx * self.speed * dt
        self.y += vy * self.speed * dt

        # Keep inside bounds
        self.x = max(0, min(self.x, MAP_WIDTH * TILE_SIZE - self.width))
        self.y = max(0, min(self.y, MAP_HEIGHT * TILE_SIZE - self.height))

        for block in area.obstacles():
            if self.rect.colliderect(block):
                # Basic resolution
                if vx > 0:
                    self.x = block.left - self.width
                elif vx < 0:
                    self.x = block.right
                if vy > 0:
                    self.y = block.top - self.height
                elif vy < 0:
                    self.y = block.bottom

        if keys[pygame.K_SPACE] and self.attack_timer <= 0:
            self.attack_timer = self.attack_cooldown
            game.messages.append("Sword slash! Any nearby enemies will feel that.")
            attack_area = self.attack_rect()
            for enemy in area.enemies:
                if enemy.alive and attack_area.colliderect(enemy.rect):
                    enemy.alive = False
                    game.messages.append(f"You defeated a {enemy.__class__.__name__}!")


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Riverwake: 8-bit Adventure")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.big_font = pygame.font.Font(None, 32)
        self.map_manager = MapManager(self.create_world())
        self.player = Player(6 * TILE_SIZE, 7 * TILE_SIZE)
        self.inventory = {"iron_sword"}
        self.messages: List[str] = [
            "You wake in Sunhaven Town after fending off raiders. The Celest River runs wild.",
            "Find Mayor Lysa in the town hall to learn what remains of the quest."
        ]
        self.story_stage = 1  # mid-game start
        self.transitioning = False
        self.slide_offset = 0
        self.slide_direction = ""
        self.slide_target: Optional[str] = None

    def create_world(self) -> Dict[str, Area]:
        def layout_from_rows(rows: List[str]) -> List[str]:
            return [row.ljust(MAP_WIDTH, "G")[:MAP_WIDTH] for row in rows[:MAP_HEIGHT]]

        def base_grass() -> List[str]:
            return ["G" * MAP_WIDTH for _ in range(MAP_HEIGHT)]

        def carve_river(layout: List[str], bridges: List[int]) -> List[str]:
            grid = [list(r) for r in layout]
            for y in range(MAP_HEIGHT):
                for x in [9, 10]:
                    grid[y][x] = "W"
            for y in bridges:
                for x in [9, 10]:
                    grid[y][x] = "H"
            return ["".join(r) for r in grid]

        def add_road(layout: List[str], cols: List[int], rows: List[int]) -> List[str]:
            grid = [list(r) for r in layout]
            for y in rows:
                for x in range(MAP_WIDTH):
                    grid[y][x] = "R"
            for x in cols:
                for y in range(MAP_HEIGHT):
                    grid[y][x] = "R"
            return ["".join(r) for r in grid]

        def paint_rect(layout: List[str], rect: pygame.Rect, char: str) -> List[str]:
            grid = [list(r) for r in layout]
            for y in range(rect.top, rect.bottom):
                for x in range(rect.left, rect.right):
                    if 0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT:
                        grid[y][x] = char
            return ["".join(r) for r in grid]

        def add_trees(layout: List[str], density: float = 0.12) -> List[str]:
            grid = [list(r) for r in layout]
            for y in range(MAP_HEIGHT):
                for x in range(MAP_WIDTH):
                    if grid[y][x] == "G" and random.random() < density:
                        grid[y][x] = "T"
            return ["".join(r) for r in grid]

        areas: Dict[str, Area] = {}

        # Sunhaven Town (1,1)
        town = carve_river(base_grass(), bridges=[6, 7])
        town = add_road(town, cols=[4, 15], rows=[7])
        town = paint_rect(town, pygame.Rect(1, 3, 5, 4), "B")  # Town hall walls
        town = paint_rect(town, pygame.Rect(2, 4, 3, 2), "F")
        town = paint_rect(town, pygame.Rect(2, 6, 1, 1), "D")
        town = paint_rect(town, pygame.Rect(14, 3, 5, 4), "B")  # Inn walls
        town = paint_rect(town, pygame.Rect(15, 4, 3, 2), "F")
        town = paint_rect(town, pygame.Rect(15, 6, 1, 1), "D")
        town = paint_rect(town, pygame.Rect(7, 11, 6, 2), "R")
        town = paint_rect(town, pygame.Rect(0, 12, 20, 3), "S")  # plaza sand edge

        town_npcs = [
            NPC(x=2 * TILE_SIZE, y=5 * TILE_SIZE, speed=0, name="Mayor Lysa", lines=[
                "You survived the raid, hero.",
                "The river is surging with lunar energy. Our lighthouse is dark.",
                "Take the Forest Pass from Ranger Thom west of town, then retrieve the lantern from the quarry.",
                "Once you carry the Shell Key, unlock the coast ruins and rekindle the lighthouse with the Ocean Heart."
            ], give_item=None, required_stage=1, set_stage=2, once=True),
            NPC(x=16 * TILE_SIZE, y=5 * TILE_SIZE, speed=0, name="Innkeeper Mira", lines=[
                "Rest easy. I stitched your cloak while you were out cold.",
                "If you need direction: west is forest, north the ridge, east the beach road, south the plains."
            ], once=True),
            NPC(x=5 * TILE_SIZE, y=11 * TILE_SIZE, speed=0, name="Child", lines=[
                "When the lighthouse was bright, the stars danced on the waves!"
            ], once=False)
        ]

        town_portals = {
            (2, 6): Portal(area="town_hall", spawn=(3, 9), message="You step inside the town hall."),
            (15, 6): Portal(area="inn", spawn=(3, 9), message="You step into the inn's hearth glow."),
        }

        areas["1,1"] = Area(
            key="1,1",
            name="Sunhaven Town",
            biome="town",
            layout=town,
            npcs=town_npcs,
            portals=town_portals,
            edge_locks={"left": ("forest_pass", "A ranger blocks the gate: 'Pass required for the wildwood.'")},
        )

        # Westwood Gate (0,1)
        forest_gate = add_trees(carve_river(base_grass(), bridges=[7]), density=0.25)
        forest_gate = add_road(forest_gate, cols=[4], rows=[7])
        forest_gate = paint_rect(forest_gate, pygame.Rect(0, 0, 3, 15), "T")
        forest_gate_npcs = [
            NPC(x=3 * TILE_SIZE, y=7 * TILE_SIZE, speed=0, name="Ranger Thom", lines=[
                "Mayor said you'd help? Good. We cannot hold the forest alone.",
                "Take this Forest Pass—stay on the road and the trees may whisper less."
            ], give_item="forest_pass", required_stage=2, set_stage=3, once=True)
        ]
        areas["0,1"] = Area(
            key="0,1",
            name="Westwood Gate",
            biome="forest",
            layout=forest_gate,
            npcs=forest_gate_npcs,
            edge_locks={},
        )

        # Deep Woods (0,2)
        woods = add_trees(carve_river(base_grass(), bridges=[5, 12]), density=0.35)
        woods = add_road(woods, cols=[4], rows=[])
        woods_enemies = [Enemy(x=2 * TILE_SIZE, y=10 * TILE_SIZE, base_x=2 * TILE_SIZE, base_y=10 * TILE_SIZE, speed=0),
                         Enemy(x=6 * TILE_SIZE, y=4 * TILE_SIZE, base_x=6 * TILE_SIZE, base_y=4 * TILE_SIZE, speed=0)]
        areas["0,2"] = Area(
            key="0,2",
            name="Deep Woods",
            biome="forest",
            layout=woods,
            enemies=woods_enemies,
            edge_locks={},
        )

        # Misty Ridge (0,0)
        ridge = add_trees(carve_river(base_grass(), bridges=[2, 10]), density=0.22)
        ridge = paint_rect(ridge, pygame.Rect(12, 0, 8, 5), "M")
        ridge = add_road(ridge, cols=[4], rows=[])
        ridge_npcs = [NPC(x=5 * TILE_SIZE, y=2 * TILE_SIZE, speed=0, name="Miner Cato", lines=[
            "Quarry tunnels are choked in moon-ash.",
            "Take my ember lantern; it cuts through the haze."
        ], give_item="ember_lantern", required_stage=3, set_stage=4, once=True)]
        areas["0,0"] = Area(
            key="0,0",
            name="Misty Ridge Quarry",
            biome="quarry",
            layout=ridge,
            npcs=ridge_npcs,
            edge_locks={},
        )

        # River Bend (1,0)
        bend = carve_river(base_grass(), bridges=[3, 11])
        bend = add_road(bend, cols=[4, 15], rows=[7])
        bend = paint_rect(bend, pygame.Rect(0, 0, 5, 4), "M")
        bend_enemies = [Enemy(x=12 * TILE_SIZE, y=3 * TILE_SIZE, base_x=12 * TILE_SIZE, base_y=3 * TILE_SIZE, patrol_range=20)]
        areas["1,0"] = Area(
            key="1,0",
            name="River Bend",
            biome="river",
            layout=bend,
            enemies=bend_enemies,
        )

        # Northern Ruins (2,0)
        ruins = carve_river(base_grass(), bridges=[7])
        ruins = paint_rect(ruins, pygame.Rect(0, 0, 6, 3), "M")
        ruins = paint_rect(ruins, pygame.Rect(6, 0, 6, 3), "S")
        ruins = paint_rect(ruins, pygame.Rect(6, 3, 6, 3), "T")
        ruins = paint_rect(ruins, pygame.Rect(14, 0, 6, 5), "S")
        ruins = add_road(ruins, cols=[15], rows=[7])
        ruins = paint_rect(ruins, pygame.Rect(15, 4, 2, 2), "D")
        ruins_npcs = [NPC(x=15 * TILE_SIZE, y=5 * TILE_SIZE, speed=0, name="Seeker Lyra", lines=[
            "A stone gate bars the coast temple. Legend says a Shell Key unseals it.",
            "With the conch crest in hand, claim the Ocean Heart from the ruin's altar and wake the lighthouse."
        ], give_item="ocean_heart", required_stage=5, once=True)]
        areas["2,0"] = Area(
            key="2,0",
            name="Northern Ruins",
            biome="ruins",
            layout=ruins,
            npcs=ruins_npcs,
            edge_locks={},
        )

        # Storm Cliffs (3,0)
        cliffs = carve_river(base_grass(), bridges=[6])
        cliffs = paint_rect(cliffs, pygame.Rect(0, 0, 20, 3), "M")
        cliffs = paint_rect(cliffs, pygame.Rect(13, 3, 7, 12), "S")
        cliffs_enemies = [Enemy(x=12 * TILE_SIZE, y=9 * TILE_SIZE, base_x=12 * TILE_SIZE, base_y=9 * TILE_SIZE, patrol_range=18)]
        areas["3,0"] = Area(
            key="3,0",
            name="Storm Cliffs",
            biome="coast",
            layout=cliffs,
            enemies=cliffs_enemies,
        )

        # Eastern Farms (2,1)
        farms = carve_river(base_grass(), bridges=[6])
        farms = add_road(farms, cols=[15], rows=[7])
        farms = paint_rect(farms, pygame.Rect(16, 8, 4, 4), "S")
        farms = paint_rect(farms, pygame.Rect(0, 12, 8, 3), "S")
        farms = paint_rect(farms, pygame.Rect(12, 4, 4, 2), "B")
        farms = paint_rect(farms, pygame.Rect(13, 5, 2, 1), "D")
        farms_npcs = [NPC(x=17 * TILE_SIZE, y=9 * TILE_SIZE, speed=0, name="Farmer Oda", lines=[
            "River soaked my fields, but the sand patch held. The ocean breeze is sweet today."
        ], once=False)]
        areas["2,1"] = Area(
            key="2,1",
            name="Eastern Farms",
            biome="plains",
            layout=farms,
            npcs=farms_npcs,
            edge_locks={"right": ("shell_key", "A tide-locked gate needs the Shell Key."), "up": ("shell_key", "The coastal ruins are sealed by a shell crest.")},
        )

        # Tidal Beach (3,1)
        beach = carve_river(base_grass(), bridges=[7])
        beach = paint_rect(beach, pygame.Rect(12, 0, 8, 15), "S")
        beach = paint_rect(beach, pygame.Rect(14, 4, 4, 3), "W")
        beach = paint_rect(beach, pygame.Rect(14, 7, 4, 2), "H")
        beach_npcs = [NPC(x=13 * TILE_SIZE, y=10 * TILE_SIZE, speed=0, name="Beach Hermit", lines=[
            "I watched the stars fall into the bay.",
            "Take this Shell Key—only one who defied the raiders deserves it."
        ], give_item="shell_key", required_stage=4, set_stage=5, once=True)]
        areas["3,1"] = Area(
            key="3,1",
            name="Tidal Beach",
            biome="coast",
            layout=beach,
            npcs=beach_npcs,
            edge_locks={
                "up": ("shell_key", "A carved conch symbol shimmers: key required."),
                "right": ("shell_key", "The lighthouse gate needs the Shell Key."),
                "down": ("shell_key", "A tidal lock bars the way south without the Shell Key."),
            },
        )

        # River Plains (1,2)
        plains = carve_river(base_grass(), bridges=[3, 10, 12])
        plains = add_road(plains, cols=[4, 15], rows=[7])
        plains = paint_rect(plains, pygame.Rect(0, 11, 20, 4), "S")
        plains_enemies = [Enemy(x=5 * TILE_SIZE, y=9 * TILE_SIZE, base_x=5 * TILE_SIZE, base_y=9 * TILE_SIZE, patrol_range=26)]
        areas["1,2"] = Area(
            key="1,2",
            name="River Plains",
            biome="plains",
            layout=plains,
            enemies=plains_enemies,
        )

        # Ruin Approach (2,2)
        approach = carve_river(base_grass(), bridges=[7, 10])
        approach = add_road(approach, cols=[15], rows=[7])
        approach = paint_rect(approach, pygame.Rect(0, 0, 8, 4), "T")
        approach = paint_rect(approach, pygame.Rect(0, 11, 8, 4), "T")
        approach_enemies = [Enemy(x=10 * TILE_SIZE, y=5 * TILE_SIZE, base_x=10 * TILE_SIZE, base_y=5 * TILE_SIZE, patrol_range=20)]
        areas["2,2"] = Area(
            key="2,2",
            name="Ruin Approach",
            biome="plains",
            layout=approach,
            enemies=approach_enemies,
            edge_locks={"down": ("ember_lantern", "A wall of moon-ash blinds the way. Light pierces it."), "right": ("shell_key", "Sealed until the Shell Key gleams.")},
        )

        # Lighthouse Shore (3,2)
        shore = carve_river(base_grass(), bridges=[7])
        shore = paint_rect(shore, pygame.Rect(12, 0, 8, 15), "S")
        shore = paint_rect(shore, pygame.Rect(12, 6, 6, 3), "B")
        shore = paint_rect(shore, pygame.Rect(14, 7, 2, 1), "D")
        areas["3,2"] = Area(
            key="3,2",
            name="Lighthouse Shore",
            biome="coast",
            layout=shore,
            portals={(14, 7): Portal(area="lighthouse", spawn=(10, 10), message="You unlock the lighthouse door and step inside.")},
        )

        # Interiors
        hall_layout = layout_from_rows([
            "BBBBBBBBBBBBBBBBBBBB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFRRFFFFFRRFFFFF B".replace(" ", "B"),
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFTTFFFFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BBBBBBBBBBDDBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
        ])

        inn_layout = layout_from_rows([
            "BBBBBBBBBBBBBBBBBBBB",
            "BFFFFFBBFFFFFBBBBBBB",
            "BFFFFFBBFFFFFBBBBBBB",
            "BFFFFFBBFFFFFBBBBBBB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BBBBBBBBBBDDBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
        ])

        lighthouse_layout = layout_from_rows([
            "BBBBBBBBBBBBBBBBBBBB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BFFFFFRRRRFFFFFFFFFB",
            "BFFFFFFFFFFFFFFFFFFB",
            "BBBBBBBBBBDDBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
            "BBBBBBBBBBBBBBBBBBBB",
        ])

        areas["town_hall"] = Area(
            key="town_hall",
            name="Sunhaven Town Hall",
            biome="interior",
            layout=hall_layout,
            npcs=[],
            portals={(10, 11): Portal(area="1,1", spawn=(2, 7), message="You return to the plaza.")},
        )

        areas["inn"] = Area(
            key="inn",
            name="Lantern's Rest Inn",
            biome="interior",
            layout=inn_layout,
            npcs=[],
            portals={(10, 11): Portal(area="1,1", spawn=(15, 7), message="You step outside into Sunhaven."),},
        )

        areas["lighthouse"] = Area(
            key="lighthouse",
            name="Luminous Lighthouse",
            biome="interior",
            layout=lighthouse_layout,
            npcs=[NPC(x=9 * TILE_SIZE, y=3 * TILE_SIZE, speed=0, name="Beacon Core", lines=[
                "An empty socket awaits the Ocean Heart."
            ])],
            portals={(10, 11): Portal(area="3,2", spawn=(14, 8), message="You step into the salt air."),},
        )

        return areas

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if event.key == pygame.K_e:
                        self.try_interact()
                    if event.key == pygame.K_SPACE and self.player.attack_timer <= 0:
                        # Attack is handled in player update, here only reset timer if not moving
                        self.player.attack_timer = 0

            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()

    def try_interact(self):
        area = self.map_manager.get_area()
        for npc in area.npcs:
            if self.player.rect.colliderect(npc.rect.inflate(10, 10)):
                message = npc.interact(self)
                self.messages.append(message)
                return
        # Portals require standing on exact tile center
        tile_pos = (self.player.rect.centerx // TILE_SIZE, self.player.rect.centery // TILE_SIZE)
        if tile_pos in area.portals:
            if area.key == "3,2" and "shell_key" not in self.inventory:
                self.messages.append("The lighthouse door is sealed by a shell-shaped crest.")
                return
            portal = area.portals[tile_pos]
            self.messages.append(portal.message)
            self.map_manager.set_current(portal.area)
            self.player.x = portal.spawn[0] * TILE_SIZE
            self.player.y = portal.spawn[1] * TILE_SIZE
            return
        if area.key == "lighthouse" and "ocean_heart" in self.inventory and self.story_stage >= 5:
            self.story_stage = 6
            self.messages.append("You place the Ocean Heart. The lighthouse beams awaken, calming the river. The journey ends in light.")

    def update(self, dt: float):
        if not self.transitioning:
            self.player.update(dt, self.map_manager.get_area(), self)
            self.handle_edges()
        else:
            self.slide_offset += dt * 240
            if self.slide_offset >= SCREEN_WIDTH:
                self.transitioning = False
                self.slide_offset = 0
                self.map_manager.set_current(self.slide_target)
                self.player.x %= MAP_WIDTH * TILE_SIZE
                self.player.y %= MAP_HEIGHT * TILE_SIZE

        # Update enemies
        area = self.map_manager.get_area()
        for enemy in area.enemies:
            enemy.update(dt, area.obstacles())

    def handle_edges(self):
        if self.transitioning:
            return
        direction = None
        if self.player.x <= 0:
            direction = "left"
            self.player.x = 0
        elif self.player.x + self.player.width >= MAP_WIDTH * TILE_SIZE:
            direction = "right"
            self.player.x = MAP_WIDTH * TILE_SIZE - self.player.width
        elif self.player.y <= 0:
            direction = "up"
            self.player.y = 0
        elif self.player.y + self.player.height >= MAP_HEIGHT * TILE_SIZE:
            direction = "down"
            self.player.y = MAP_HEIGHT * TILE_SIZE - self.player.height

        if direction:
            current_area = self.map_manager.get_area()
            if direction in current_area.edge_locks:
                item, message = current_area.edge_locks[direction]
                if item not in self.inventory:
                    self.messages.append(message)
                    return
            neighbor_key = self.map_manager.neighbor(direction)
            if neighbor_key:
                self.start_slide(direction, neighbor_key)

    def start_slide(self, direction: str, target: str):
        self.transitioning = True
        self.slide_direction = direction
        self.slide_target = target
        # Set player position to opposite side of target after slide completes
        if direction == "left":
            self.player.x = MAP_WIDTH * TILE_SIZE - self.player.width - 2
        elif direction == "right":
            self.player.x = 2
        elif direction == "up":
            self.player.y = MAP_HEIGHT * TILE_SIZE - self.player.height - 2
        elif direction == "down":
            self.player.y = 2

    def draw(self):
        self.screen.fill(Color(0, 0, 0))
        area = self.map_manager.get_area()
        base_surface = pygame.Surface((MAP_WIDTH * TILE_SIZE, MAP_HEIGHT * TILE_SIZE))
        self.draw_area(base_surface, area)
        player_surface = base_surface.copy()
        self.draw_entities(player_surface, area)

        offset_x = offset_y = 0
        if self.transitioning and self.slide_target:
            next_area = self.map_manager.get_area(self.slide_target)
            next_surface = pygame.Surface((MAP_WIDTH * TILE_SIZE, MAP_HEIGHT * TILE_SIZE))
            self.draw_area(next_surface, next_area)
            self.draw_entities(next_surface, next_area)
            if self.slide_direction == "left":
                offset_x = -self.slide_offset
                self.screen.blit(next_surface, (offset_x + MAP_WIDTH * TILE_SIZE, 0))
            elif self.slide_direction == "right":
                offset_x = self.slide_offset
                self.screen.blit(next_surface, (offset_x - MAP_WIDTH * TILE_SIZE, 0))
            elif self.slide_direction == "up":
                offset_y = -self.slide_offset * (SCREEN_HEIGHT / SCREEN_WIDTH)
                self.screen.blit(next_surface, (0, offset_y + MAP_HEIGHT * TILE_SIZE))
            elif self.slide_direction == "down":
                offset_y = self.slide_offset * (SCREEN_HEIGHT / SCREEN_WIDTH)
                self.screen.blit(next_surface, (0, offset_y - MAP_HEIGHT * TILE_SIZE))
        self.screen.blit(player_surface, (offset_x, offset_y))

        self.draw_ui()

    def draw_area(self, surface: pygame.Surface, area: Area):
        tick = pygame.time.get_ticks()
        for y, row in enumerate(area.layout):
            for x, tile in enumerate(row):
                pos = (x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                color = COLORS["grass"]
                if tile == "R":
                    color = COLORS["road"]
                elif tile == "T":
                    color = COLORS["tree"]
                elif tile == "W":
                    wave = int((math.sin((tick + x * 10) / 350) + 1) * 10)
                    color = Color(COLORS["water"]).lerp(Color(90, 180, 240), wave / 20)
                elif tile == "S":
                    color = COLORS["sand"]
                elif tile == "M":
                    color = COLORS["rock"]
                elif tile == "B":
                    color = COLORS["wall"]
                elif tile == "F":
                    color = COLORS["floor"]
                elif tile == "H":
                    color = COLORS["bridge"]
                pygame.draw.rect(surface, color, pos)
                if tile == "B":
                    roof_height = 6
                    pygame.draw.rect(surface, COLORS["roof"], (pos[0], pos[1], pos[2], roof_height))
                if tile == "T":
                    sway = math.sin((tick + x * 5) / 400) * 2
                    pygame.draw.circle(surface, Color(46, 140, 46), (pos[0] + TILE_SIZE // 2, int(pos[1] + TILE_SIZE // 2 + sway)), 6)

    def draw_entities(self, surface: pygame.Surface, area: Area):
        # NPCs
        for npc in area.npcs:
            pygame.draw.rect(surface, Color(240, 220, 120), npc.rect)
            pygame.draw.rect(surface, Color(80, 60, 30), npc.rect, 2)
        # Enemies
        for enemy in area.enemies:
            if not enemy.alive:
                continue
            color = Color(200, 60, 80)
            blink = math.sin(pygame.time.get_ticks() / 200)
            color = color.lerp(Color(255, 255, 255), (blink + 1) / 2 * 0.2)
            pygame.draw.rect(surface, color, enemy.rect)
        # Player
        frame = int(pygame.time.get_ticks() / 200) % 2
        hero_color = Color(80, 180, 255) if frame else Color(100, 200, 255)
        pygame.draw.rect(surface, hero_color, self.player.rect)
        # Attack indicator
        if self.player.attack_timer > 0:
            pygame.draw.rect(surface, Color(255, 255, 0), self.player.attack_rect(), 2)

    def draw_ui(self):
        hud = pygame.Surface((SCREEN_WIDTH, 96), pygame.SRCALPHA)
        hud.fill(Color(0, 0, 0, 130))
        area = self.map_manager.get_area()
        title = self.big_font.render(area.name, True, COLORS["ui_text"])
        hud.blit(title, (10, 5))
        inv_text = ", ".join(sorted(self.inventory))
        inv_render = self.font.render(f"Inventory: {inv_text}", True, COLORS["ui_text"])
        hud.blit(inv_render, (10, 36))
        stage_text = self.font.render(self.story_summary(), True, COLORS["ui_text"])
        hud.blit(stage_text, (10, 60))
        if self.messages:
            msg = self.messages[-1][-70:]
            msg_render = self.font.render(msg, True, COLORS["ui_text"])
            hud.blit(msg_render, (10, 80))
        self.screen.blit(hud, (0, 0))

    def story_summary(self) -> str:
        summaries = {
            1: "Start: recover, speak to Mayor Lysa in Sunhaven.",
            2: "Mid: take Forest Pass from Ranger Thom.",
            3: "Mid: travel to Misty Ridge for the ember lantern.",
            4: "Mid: reach the coast hermit for the Shell Key.",
            5: "End: unlock lighthouse and place Ocean Heart.",
            6: "Epilogue: the Celest River calms; Sunhaven rests."
        }
        return summaries.get(self.story_stage, "Explore the land.")


if __name__ == "__main__":
    game = Game()
    game.run()
