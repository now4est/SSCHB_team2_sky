from __future__ import annotations
import asyncio
import websockets
import numpy as np
from ft_player.BlockType import BlockType as bt
 
BOARD_WIDTH = 14
BOARD_HEIGHT = 14

class PlayerClient:
    def __init__(self, player_number: int, socket: websockets.WebSocketClientProtocol, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._socket = socket
        self._player_number = player_number
        self.blocks = [chr(i) for i in range(85,64,-1)]
        self.board = np.zeros((BOARD_HEIGHT, BOARD_WIDTH))
        self.turn = 0
        self.mark = None

    @property
    def player_number(self) -> int:
        return self._player_number

    async def close(self):
        await self._socket.close()

    async def play(self):
        while True:
            board = await self._socket.recv()
            board = [list(line) for line in board.split('\n')]
            self.parse_board(board)
            action = self.create_action()
            await self._socket.send(action)
            if action == 'X000':
                raise SystemExit

    def create_action(self):
        actions: list[str]
        turn: int

        if self.turn == 0:
            if self.player_number == 1:
                self.mark = 'o'
                self.turn += 1
                self.blocks.pop(0)
                return f'U045'
            else:
                self.mark = 'x'
                self.turn += 1
                self.blocks.pop(0)
                return f'U09A'
        
        self.identify_starting_points()
        block_type, x, y, action = self.find_placeable_position()
        if block_type:
            self.turn += 1
            self.blocks.remove(block_type)
            hx = f'{x+1:X}'
            hy = f'{y+1:X}'
            # print(f'{block_type}{action}{hx}{hy}')
            return f'{block_type}{action}{hx}{hy}'

        # print('X000')
        return 'X000'
    
    @staticmethod
    async def create(url: str, loop: asyncio.AbstractEventLoop) -> PlayerClient:
        socket = await websockets.connect(url)
        print('PlayerClient: connected')
        player_number = await socket.recv()
        print(f'player_number: {player_number}')
        return PlayerClient(int(player_number), socket, loop)

    def parse_board(self, board):
        for yi in range(BOARD_HEIGHT):
            for xi in range(BOARD_WIDTH):
                if board[yi+1][xi+1] == '.':
                    self.board[yi][xi] = 0
                elif board[yi+1][xi+1] == self.mark:
                    self.board[yi][xi] = 1
                else:
                    self.board[yi][xi] = 2

    def is_out_board(self, block: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
        # ボード外か
        if x+w >= BOARD_WIDTH or y+h >= BOARD_HEIGHT:
            return True
        return False

    def is_overlap(self, block: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
        # 他のブロックと重ならないか
        if np.any(self.board[y:y+h, x:x+w] + block > 1):
            return True
        return False

    def is_adjacent(self, block: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
        # 他の自ブロックと隣接しないか
        top_edge = self.board[max(0, y-1), x:x+w] == 1
        bottom_edge = self.board[min(BOARD_HEIGHT, y+h), x:x+w] == 1
        left_edge = self.board[y:y+h, max(0, x-1)] == 1
        right_edge = self.board[y:y+h, min(BOARD_WIDTH, x+w)] == 1
        if np.any(top_edge) or np.any(bottom_edge) or np.any(left_edge) or np.any(right_edge):
            return True
        return False

    def put(self, block: np.ndarray, x: int, y: int, action: int) -> bool:
        # x = int(x, 16) - 1
        # y = int(y, 16) - 1
        rotate = ((action & 6) >> 1) * -1
        block = np.rot90(block, rotate).copy()
        flip = (action & 1) == 1
        if flip:
            nblock = np.fliplr(block)
        h, w = block.shape

        if self.is_out_board(block, x, y, w, h):
            # print('error: ボード外')
            return False
        if self.is_overlap(block, x, y):
            # print('error: 重なり')
            return False
        if self.is_adjacent(block, x, y, w, h):
            # print('error: 隣接')
            return False
        self.board[y:y+h, x:x+w] += block
        return True

    def identify_starting_points(self):
        # ブロックをボードへ置く際の起点となりうる位置を探す
        # self.boardと同じサイズの0配列を作成
        self.starting_points = np.zeros((BOARD_HEIGHT, BOARD_WIDTH))

        # self.board内で1のマスに対して、斜めの位置のみが起点となりうる
        for yi in range(BOARD_HEIGHT):
            for xi in range(BOARD_WIDTH):
                if self.board[yi, xi] == 1:
                    lpos = [(yi-1, xi-1), (yi-1, xi+1), (yi+1, xi-1), (yi+1, xi+1)]
                    for pos in lpos:
                        if 0 <= pos[0] < BOARD_HEIGHT and 0 <= pos[1] < BOARD_WIDTH and self.board[pos] == 0:
                            self.starting_points[pos] += 1
    
    def gen_action(self, rotation: int, flip: bool) -> int:
        if rotation == 0 and not flip:
            return 0
        elif rotation == 0 and flip:
            return 1
        elif rotation == 1 and not flip:
            return 2
        elif rotation == 1 and flip:
            return 3
        elif rotation == 2 and not flip:
            return 4
        elif rotation == 2 and flip:
            return 5
        elif rotation == 3 and not flip:
            return 6
        elif rotation == 3 and flip:
            return 7

    def evaluate_position(self, block, nx, ny):
        # プレイヤー番号に基づいて評価関数を変更
        if self.player_number == 1:
            return nx + ny
        else:
            return - nx - ny
    
    def find_placeable_position(self):
        best_score = float('inf')
        best_position = (None, None, None, None, None)
        for block_type in self.blocks:
            block = bt[block_type].block_map
            # ブロックのすべての回転と反転を試す
            for rotation in range(4):
                for flip in [True, False]:
                    if flip:
                        block = np.flip(block, axis=1)
                    block = np.rot90(block, rotation)
                    h, w = block.shape
                    # ブロック内の各1の位置を取得
                    ones_y, ones_x = np.where(block == 1)
                    for y in range(BOARD_HEIGHT):
                        for x in range(BOARD_WIDTH):
                            # self.starting_pointsで1のポジションを走査する
                            if self.starting_points[y, x] == 1:
                                # ブロック内の各1の位置を起点として試す
                                for oy, ox in zip(ones_y, ones_x):
                                    ny, nx = y - oy, x - ox
                                    # ny, nxがボード内に収まっていることを確認
                                    if ny < 0 or ny >= BOARD_HEIGHT or nx < 0 or nx >= BOARD_WIDTH:
                                        continue
                                    if self.is_out_board(block, nx, ny, w, h):
                                        continue
                                    if self.is_overlap(block, nx, ny, w, h):
                                        continue
                                    if self.is_adjacent(block, nx, ny, w, h):
                                        continue
                                    # 評価関数を用いてスコアを計算
                                    score = self.evaluate_position(block, nx, ny)
                                    # 最良のスコアよりも良い場合は更新
                                    if score < best_score:
                                        best_score = score
                                        best_position = (block_type, nx, ny, rotation, flip)
        return best_position

