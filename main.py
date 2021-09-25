import os
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from random import shuffle
from typing import List

from cryptography.fernet import Fernet

sys.setrecursionlimit(10 ** 7)
threading.stack_size(2 ** 27)

FILEPATH = os.pardir
SAVES_FOLDER_NAME = 'minesweeper-saves'
CRYPTO_KEY = b'5DpjFVH2RkNa8DDU0GAwpOxVBWY-PxSiQZqwx2HMD9A='


class CellState(Enum):
    CLOSED = 0
    FLAGGED = 1
    OPENED = 2


@dataclass
class Cell:
    state: CellState = CellState.CLOSED

    @property
    def is_closed(self):
        return self.state == CellState.CLOSED

    @property
    def is_flagged(self):
        return self.state == CellState.FLAGGED

    @property
    def is_opened(self):
        return self.state == CellState.OPENED

    is_bomb: bool = False


class GameStatus(Enum):
    STARTED = 0
    LOST = 1
    WON = 2
    NOT_STARTED = 3


class MessageType(Enum):
    SUCCESS_TURN = 0
    FAILED_TURN = 1
    LOST = 2
    WON = 3
    INITIAL = 4


@dataclass
class Message:
    type: MessageType
    field: List[List[Cell]]
    error_message: str = None


def game_from_save(save_string):
    splitted_save_string = save_string.split()
    game_id = int(splitted_save_string[0])
    status = GameStatus(int(splitted_save_string[1]))
    field_size_x = int(splitted_save_string[2])
    field_size_y = int(splitted_save_string[3])
    bombs_num = int(splitted_save_string[4])
    raw_field = splitted_save_string[5]
    field = [[Cell() for _ in range(field_size_x)] for _ in range(field_size_y)]
    for y, row in enumerate(raw_field.split('#')):
        for x, cell in enumerate(row.split(';')):
            if cell:
                field[y][x].state = CellState(int(cell.split(',')[0]))
                field[y][x].is_bomb = bool(int(cell.split(',')[1]))
    game = Game(game_id, 1, 1, 0)
    game.field = field
    game.status = status
    game.bombs_num = bombs_num
    return game


class Game:
    def __init__(self, game_id, field_width, field_height, bombs_num):
        assert bombs_num < (field_height * field_width)
        assert field_height > 0 and field_width > 0
        self.game_id = game_id
        self.bombs_num = bombs_num
        cells = [Cell(is_bomb=True) for _ in range(bombs_num)] \
                + [Cell(is_bomb=False) for _ in range(field_height * field_width - bombs_num)]
        shuffle(cells)
        self.field = [[cells[y * field_width + x] for x in range(field_width)] for y in range(field_height)]

    def generate_bombs(self, empty_x, empty_y):
        cells = [Cell(is_bomb=True) for _ in range(self.bombs_num)] \
                + [Cell(is_bomb=False) for _ in range(self.field_size[1] * self.field_size[0] - self.bombs_num - 1)]
        shuffle(cells)
        cells.insert(empty_y * self.field_size[0] + empty_x, Cell(is_bomb=False))
        self.field = [[cells[y * self.field_size[0] + x] for x in range(self.field_size[0])] for y in
                      range(self.field_size[1])]

    game_id: int
    bombs_num: int
    field: List[List[Cell]]
    status: GameStatus = GameStatus.NOT_STARTED

    def current_state(self):
        if self.status == GameStatus.LOST:
            return Message(MessageType.LOST, self.field)
        if self.status == GameStatus.WON:
            return Message(MessageType.WON, self.field)
        return Message(MessageType.INITIAL, self.field)

    def get_bombs_number(self, x, y):
        bomb_num = 0
        for xd in range(-1, 2):
            for yd in range(-1, 2):
                nx = x + xd
                ny = y + yd
                if 0 <= nx < self.field_size[0] and 0 <= ny < self.field_size[1]:
                    bomb_num += self.field[ny][nx].is_bomb
        return bomb_num

    def cells_around(self, x, y):
        ans = []
        for xd in range(-1, 2):
            for yd in range(-1, 2):
                nx = x + xd
                ny = y + yd
                if 0 <= nx < self.field_size[0] and 0 <= ny < self.field_size[1]:
                    ans += [[nx, ny]]
        return ans

    @property
    def field_size(self):
        return len(self.field[0]), len(self.field)

    def process_command(self, x: int, y: int, command: str):
        if x < 0 or x >= self.field_size[0]:
            return Message(type=MessageType.FAILED_TURN, error_message='Invalid X coordinate value', field=self.field)

        if y < 0 or y >= self.field_size[1]:
            return Message(type=MessageType.FAILED_TURN, error_message='Invalid Y coordinate value', field=self.field)

        if command.lower() not in ['flag', 'open']:
            return Message(type=MessageType.FAILED_TURN, error_message='Invalid command', field=self.field)

        if self.status == GameStatus.LOST:
            return Message(type=MessageType.FAILED_TURN, error_message='Sorry, you have already lost.',
                           field=self.field)

        if self.status == GameStatus.WON:
            return Message(type=MessageType.FAILED_TURN, error_message='You have already won, congrats!',
                           field=self.field)

        if command.lower() == 'flag':
            return self.flag_cell(x, y)
        else:
            if self.status == GameStatus.NOT_STARTED:
                self.generate_bombs(x, y)
                self.status = GameStatus.STARTED
                return self.open_cell(x, y)
            else:
                return self.open_cell(x, y)

    def is_win(self):
        for y in range(self.field_size[1]):
            for x in range(self.field_size[0]):
                cell = self.field[y][x]
                if cell.is_bomb and not cell.is_flagged:
                    return False
                if not cell.is_bomb and not cell.is_opened:
                    return False
        return True

    def win(self):
        self.status = GameStatus.WON
        return Message(type=MessageType.WON, field=self.field)

    def flag_cell(self, x, y):
        if self.field[y][x].is_opened:
            return Message(type=MessageType.FAILED_TURN, field=self.field, error_message='You can\'t flag opened cell')
        self.field[y][x].state = CellState.CLOSED if self.field[y][x].is_flagged else CellState.FLAGGED
        if self.is_win():
            return self.win()
        return Message(type=MessageType.SUCCESS_TURN, field=self.field)

    def hint(self):
        def remove_duplicates(l):
            return list(set(l))

        suspect_groups = []
        for y in range(self.field_size[1]):
            for x in range(self.field_size[0]):
                cell = self.field[y][x]
                if cell.is_opened and self.get_bombs_number(x, y) != 0:
                    suspect_cells = set()
                    for suspect_cell in self.cells_around(x, y):
                        if not self.field[suspect_cell[1]][suspect_cell[0]].is_opened:
                            suspect_cells.add((suspect_cell[0], suspect_cell[1]))
                    suspect_cells = frozenset(suspect_cells)
                    if len(suspect_cells) != 0:
                        suspect_groups.append((suspect_cells, self.get_bombs_number(x, y)))
        flag = True
        suspect_groups = remove_duplicates(suspect_groups)
        while flag:
            flag = False
            for i in range(len(suspect_groups)):
                for j in range(i + 1, len(suspect_groups)):
                    g1 = suspect_groups[i]
                    g2 = suspect_groups[j]
                    if g1[0] < g2[0] or g1[0] > g2[0]:
                        if g1[0] > g2[0]:
                            a, b = (j, i)
                            g1, g2 = g2, g1
                        else:
                            a, b = (i, j)
                        suspect_groups[b] = (g2[0] - g1[0], g2[1] - g1[1])
                        flag = True
                        continue
                    if len(g1[0] & g2[0]) > 0 and g1 != g2:
                        intersection = g1[0] & g2[0]
                        if g1[1] > g2[1]:
                            a, b = (j, i)
                            g1, g2 = g2, g1
                        else:
                            a, b = (i, j)

                        if g1[1] - len(g1[0] - intersection) == g2[1]:
                            suspect_groups[b] = (intersection, g2[1])
                            suspect_groups.append((g2[0] - intersection, 0))
                            flag = True
                            continue
            suspect_groups = remove_duplicates(suspect_groups)
        for group in suspect_groups:
            if group[1] == 0 and len(group[0]) > 0:
                return self.open_cell(*(list(group[0])[0]))
            if len(group[0]) == group[1] and len(group[0]) != 0:
                for cell in group[0]:
                    if not self.field[cell[1]][cell[0]].is_flagged:
                        return self.flag_cell(*(list(group[0])[0]))
        return Message(type=MessageType.FAILED_TURN, field=self.field, error_message='No helping suggestions')

    def open_cell(self, x, y):
        if self.field[y][x].is_opened:
            return Message(type=MessageType.FAILED_TURN, field=self.field, error_message='This cell is already opened')
        self.field[y][x].state = CellState.OPENED
        if self.get_bombs_number(x, y) == 0:
            cells_around = self.cells_around(x, y)
            for zx, zy in cells_around:
                self.open_cell(zx, zy)
        if self.field[y][x].is_bomb:
            self.status = GameStatus.LOST
            return Message(type=MessageType.LOST, field=self.field)
        else:
            if self.is_win():
                return self.win()
            return Message(type=MessageType.SUCCESS_TURN, field=self.field)

    def save_string(self):
        field_string = ''
        for y in range(self.field_size[1]):
            for x in range(self.field_size[0]):
                field_string += f'{self.field[y][x].state.value},{int(self.field[y][x].is_bomb)};'
            field_string += '#'
        save_string = f'{self.game_id} {self.status.value} {self.field_size[0]} {self.field_size[1]} {self.bombs_num} {field_string}'
        return save_string


def encrypt_string(string: str):
    fernet = Fernet(CRYPTO_KEY)
    encrypted = fernet.encrypt(string.encode())
    return encrypted


def decrypt_string(encrypted_bytes):
    fernet = Fernet(CRYPTO_KEY)
    string = fernet.decrypt(encrypted_bytes).decode()
    return string


class Settings:
    def __init__(self):
        Path(f"./{SAVES_FOLDER_NAME}").mkdir(parents=True, exist_ok=True)
        open(f'./{SAVES_FOLDER_NAME}/settings.txt', 'a+').close()
        raw_settings = open(f'./{SAVES_FOLDER_NAME}/settings.txt', 'r+')
        settings = {e.split('=')[0]: eval(''.join(e.split('=')[1:])) for e in raw_settings.readlines() if
                    len(e.split('=')) > 1}
        if 'games_created' in settings:
            self.games_created = settings['games_created']
            self.games_ids = settings['games_ids']

    def save_settings(self):
        settings_file = open(f'./{SAVES_FOLDER_NAME}/settings.txt', 'w+')
        settings_file.write(f'games_created={self.games_created}\n')
        settings_file.write(f'games_ids={self.games_ids}\n')

    games_created = 0
    games_ids = []

    def create_save(self, game: Game, game_id: int):
        if game_id not in self.games_ids:
            self.games_created += 1
        self.games_ids = list(set(self.games_ids) | {game_id})
        with open(f'./{SAVES_FOLDER_NAME}/save_{game_id}', 'wb+') as save_file:
            save_file.write(encrypt_string(game.save_string()))
        self.save_settings()

    def from_save(self, game_id):
        try:
            with open(f'./{SAVES_FOLDER_NAME}/save_{game_id}', 'rb+') as save_file:
                save_string = decrypt_string(save_file.read())
            game = game_from_save(save_string)
            return game
        except Exception as e:
            print('No save found, try another number')
            self.games_ids.remove(game_id)


class UserInteractionState(Enum):
    MENU = 0
    GAME_RUNNING = 1


class UserInteraction:
    settings: Settings = Settings()

    def list_saves(self):
        saves = self.settings.games_ids
        if len(saves) == 0:
            print('There are no available saves')
            print('To create new game enter "n"')
        else:
            print(f'Select game by writing its number or create new one by writing "n"')
            for game_id in saves:
                game = self.settings.from_save(game_id)
                print(
                    f'Game {game.game_id}: {game.field_size[0]} x {game.field_size[1]}, {game.bombs_num} bomb{"s" if game.bombs_num != 1 else ""} {game.status.name.replace("_", " ")}')

    state: UserInteractionState = UserInteractionState.MENU
    current_game: Game
    current_game_id: int

    def print_game_message(self, message):
        for y in range(self.current_game.field_size[1] - 1, -1, -1):
            print(str(y).rjust(len(str(self.current_game.field_size[1] - 1))), end=' ')
            for x in range(self.current_game.field_size[0]):
                cell = self.current_game.field[y][x]
                if cell.is_opened:
                    if cell.is_bomb:
                        print('*', end='')
                    else:
                        n = self.current_game.get_bombs_number(x, y)
                        print(n if n > 0 else '·', end='')
                else:
                    if cell.is_flagged:
                        print('^', end='')
                    else:
                        print('#', end='')
            print('')

        print(' ' * (1 + len(str(self.current_game.field_size[1] - 1))), end='')
        for x in range(self.current_game.field_size[0]):
            print(x % 10, end='')
        print('')

        if message.type == MessageType.FAILED_TURN:
            print(message.error_message)

        if message.type == MessageType.WON:
            print("٩(＾◡＾)۶ Congrats! You won!")
        if message.type == MessageType.LOST:
            print("(╥﹏╥) Unfortunately! You lost!")

        if message.type == MessageType.INITIAL:
            print('To make a move write "X Y open/flag"')

        if message.type in [MessageType.WON, MessageType.LOST, MessageType.INITIAL]:
            print('To exit this game in order to create new one or select another write "e"')

    def start(self):
        print('''
  __  __ _
 |  \/  (_)
 | \  / |_ _ __   ___  _____      _____  ___ _ __   ___ _ __
 | |\/| | | '_ \ / _ \/ __\ \ /\ / / _ \/ _ \ '_ \ / _ \ '__|
 | |  | | | | | |  __/\__ \\\\ V  V /  __/  __/ |_) |  __/ |
 |_|  |_|_|_| |_|\___||___/ \_/\_/ \___|\___| .__/ \___|_|
                                            | |
                                            |_|
        ''')
        while True:
            if self.state == UserInteractionState.MENU:
                self.list_saves()
            input_string = input().strip().lower()
            if self.state == UserInteractionState.MENU:
                if input_string == 'n':
                    x_field_size = None
                    while not isinstance(x_field_size, int):
                        x_field_size = int(input("Enter field width: "))
                    y_field_size = None
                    while not isinstance(y_field_size, int):
                        y_field_size = int(input("Enter field height: "))
                    bombs_num = None
                    while not isinstance(bombs_num, int):
                        bombs_num = int(input("Enter mines number: "))
                    self.current_game_id = self.settings.games_created
                    self.current_game = Game(self.current_game_id, x_field_size, y_field_size, bombs_num)
                    self.settings.create_save(self.current_game, self.settings.games_created)
                    self.state = self.state.GAME_RUNNING
                    self.print_game_message(self.current_game.current_state())
                    self.settings.create_save(self.current_game, self.current_game_id)
                elif input_string.isdigit():
                    game_id = int(input_string)
                    try:
                        game = self.settings.from_save(game_id)
                        self.current_game_id = game_id
                        self.current_game = game
                        self.state = UserInteractionState.GAME_RUNNING
                        self.print_game_message(self.current_game.current_state())
                    except Exception as e:
                        pass
            else:
                if input_string == 'e':
                    self.state = UserInteractionState.MENU
                    self.settings.create_save(self.current_game, self.current_game_id)
                    continue
                if len(input_string.split()) == 3 and input_string.split()[0].isdigit() and \
                        input_string.split()[1].isdigit() and input_string.split()[2].lower() in ['flag', 'open']:
                    x = int(input_string.split()[0])
                    y = int(input_string.split()[1])
                    command = input_string.split()[2]
                    message = self.current_game.process_command(x, y, command)
                    self.print_game_message(message)
                    self.settings.create_save(self.current_game, self.current_game_id)
                    continue
                if input_string == 'h':
                    self.print_game_message(self.current_game.hint())
                    self.settings.create_save(self.current_game, self.current_game_id)
                    continue
                print('Your command is invalid. It should look like this: "X Y open/flag" or "e" or "h"')


if __name__ == '__main__':
    interaction = UserInteraction()
    interaction.start()
