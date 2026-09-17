import math
import random
import time
from typing import List, Tuple, Dict, Optional


class ShopifyOrderItem:
    __slots__ = ('item_id', 'order_id', 'w', 'h', 'is_filler', 'can_rotate', 'force_rotation')
    
    def __init__(self, item_id: str, order_id: str, w: int, h: int, is_filler: bool = False, can_rotate: bool = True):
        self.item_id = item_id
        self.order_id = order_id
        self.w = w
        self.h = h
        self.is_filler = is_filler
        self.can_rotate = can_rotate
        self.force_rotation = False

class PlacedItem:
    __slots__ = ('item_id', 'order_id', 'x', 'y', 'w', 'h', 'rotated')
    
    def __init__(self, item: ShopifyOrderItem, x: int, y: int, w: int, h: int, rotated: bool):
        self.item_id = item.item_id
        self.order_id = item.order_id
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.rotated = rotated

class FreeRect:
    __slots__ = ('x', 'y', 'w', 'h')
    
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def contains(self, other: 'FreeRect') -> bool:
        return (self.x <= other.x and 
                self.y <= other.y and 
                self.x + self.w >= other.x + other.w and 
                self.y + self.h >= other.y + other.h)

class LabelSheet:
    __slots__ = ('width', 'height', 'placed_items', 'free_rectangles')
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.placed_items: List[PlacedItem] = []
        self.free_rectangles: List[FreeRect] = [FreeRect(0, 0, width, height)]

    def get_density(self) -> float:
        if not self.placed_items: return 0.0
        used_area = sum(p.w * p.h for p in self.placed_items)
        return used_area / (self.width * self.height)

    def snapshot(self) -> Tuple[int, List[FreeRect]]:
        return (len(self.placed_items), list(self.free_rectangles))

    def restore(self, state: Tuple[int, List[FreeRect]]):
        placed_len, free_rects = state
        del self.placed_items[placed_len:]
        self.free_rectangles = list(free_rects)


class MaxRectsEngine:
    def __init__(self, sheet_width: int, sheet_height: int):
        self.sheet_w = sheet_width
        self.sheet_h = sheet_height

    def pack_sequence(self, sorted_orders: List[List[ShopifyOrderItem]],
                       atomic: bool = True) -> List[LabelSheet]:
        sheets = [LabelSheet(self.sheet_w, self.sheet_h)]

        if not atomic:
            for order_items in sorted_orders:
                for item in order_items:
                    self._try_commit_item(item, sheets)
            return sheets

        for order_items in sorted_orders:
            success = self._try_commit_order(order_items, sheets)
            if not success:
                pass
        return sheets

    def _try_commit_item(self, item: ShopifyOrderItem, sheets: List[LabelSheet]) -> bool:
        if self._attempt_placement(item, sheets):
            return True
        new_sheet = LabelSheet(self.sheet_w, self.sheet_h)
        if self._attempt_placement_single(item, new_sheet):
            sheets.append(new_sheet)
            return True
        return False

    def _try_commit_order(self, order_items: List[ShopifyOrderItem], sheets: List[LabelSheet]) -> bool:
        for sheet in sheets:
            state = sheet.snapshot()
            if all(self._attempt_placement_single(item, sheet) for item in order_items):
                return True
            sheet.restore(state)

        new_sheet = LabelSheet(self.sheet_w, self.sheet_h)
        if all(self._attempt_placement_single(item, new_sheet) for item in order_items):
            sheets.append(new_sheet)
            return True

        return False

    def _attempt_placement_single(self, item: ShopifyOrderItem, sheet: LabelSheet) -> bool:
        best_node, rotated = self._find_bottom_left_fit(item, sheet.free_rectangles)
        if best_node:
            w, h = (item.h, item.w) if rotated else (item.w, item.h)
            placed = PlacedItem(item, best_node.x, best_node.y, w, h, rotated)
            sheet.placed_items.append(placed)
            self._split_free_rectangles(sheet, placed)
            self._prune_enclosed_rectangles(sheet)
            return True
        return False

    def _attempt_placement(self, item: ShopifyOrderItem, sheets: List[LabelSheet]) -> bool:
        for sheet in sheets:
            if self._attempt_placement_single(item, sheet):
                return True
        return False

    def _find_bottom_left_fit(self, item: ShopifyOrderItem, free_rects: List[FreeRect]) -> Tuple[Optional[FreeRect], bool]:
        best_node = None
        best_y, best_x = float('inf'), float('inf')
        is_rotated = False

        for rect in free_rects:
            if not item.force_rotation and item.w <= rect.w and item.h <= rect.h:
                if rect.y < best_y or (rect.y == best_y and rect.x < best_x):
                    best_node, best_y, best_x, is_rotated = rect, rect.y, rect.x, False
            
            if item.can_rotate and item.h <= rect.w and item.w <= rect.h:
                if rect.y < best_y or (rect.y == best_y and rect.x < best_x):
                    best_node, best_y, best_x, is_rotated = rect, rect.y, rect.x, True

        return best_node, is_rotated

    def _split_free_rectangles(self, sheet: LabelSheet, placed: PlacedItem):
        new_rects = []
        px, py, px_end, py_end = placed.x, placed.y, placed.x + placed.w, placed.y + placed.h
        
        for rect in sheet.free_rectangles:
            rx, ry, rx_end, ry_end = rect.x, rect.y, rect.x + rect.w, rect.y + rect.h
            
            if px < rx_end and px_end > rx and py < ry_end and py_end > ry:
                if py > ry and py < ry_end:
                    new_rects.append(FreeRect(rx, ry, rect.w, py - ry))
                if py_end < ry_end:
                    new_rects.append(FreeRect(rx, py_end, rect.w, ry_end - py_end))
                if px > rx and px < rx_end:
                    new_rects.append(FreeRect(rx, ry, px - rx, rect.h))
                if px_end < rx_end:
                    new_rects.append(FreeRect(px_end, ry, rx_end - px_end, rect.h))
            else:
                new_rects.append(rect)
                
        sheet.free_rectangles = new_rects

    def _prune_enclosed_rectangles(self, sheet: LabelSheet):
        rects = sheet.free_rectangles
        keep = []
        for i, r1 in enumerate(rects):
            contained = False
            for j, r2 in enumerate(rects):
                if i != j and r2.contains(r1):
                    if r1.x == r2.x and r1.y == r2.y and r1.w == r2.w and r1.h == r2.h:
                        if j < i: 
                            contained = True
                            break
                    else:
                        contained = True
                        break
            if not contained:
                keep.append(r1)
        sheet.free_rectangles = keep


class SpaceOptimizer:
    def __init__(self, sheet_width: int, sheet_height: int):
        self.engine = MaxRectsEngine(sheet_width, sheet_height)

    def group_by_order(self, items: List[ShopifyOrderItem]) -> Dict[str, List[ShopifyOrderItem]]:
        groups = {}
        for item in items:
            groups.setdefault(item.order_id, []).append(item)
        return groups

    def get_fitness(self, sheets: List[LabelSheet]) -> float:
        return sum(sheet.get_density() ** 2 for sheet in sheets)

    def pack_deterministic(self, items: List[ShopifyOrderItem], atomic: bool = True) -> List[LabelSheet]:
        order_groups = self.group_by_order(items)
        best_layout = []
        best_fitness = -1.0

        heuristics = [
            lambda i: i.w * i.h,
            lambda i: max(i.w, i.h),
            lambda i: 2 * (i.w + i.h)
        ]

        for func in heuristics:
            for grp in order_groups.values():
                grp.sort(key=func, reverse=True)
            sorted_orders = sorted(order_groups.values(), key=lambda grp: max(func(i) for i in grp), reverse=True)

            layout = self.engine.pack_sequence(sorted_orders, atomic=atomic)
            fitness = self.get_fitness(layout)

            if fitness > best_fitness:
                best_fitness = fitness
                best_layout = layout

        return best_layout

    def pack_simulated_annealing(self, items: List[ShopifyOrderItem], max_time_seconds: float = 2.0,
                                  atomic: bool = True) -> List[LabelSheet]:

        order_groups = self.group_by_order(items)
        state_sequence = list(order_groups.values())

        best_layout = self.pack_deterministic(items, atomic=atomic)
        best_fitness = self.get_fitness(best_layout)
        
        current_sequence = state_sequence[:]
        current_fitness = best_fitness

        initial_temp = 100.0
        temp = initial_temp
        cooling_rate = 0.95
        
        start_time = time.time()
        iterations = 0

        while time.time() - start_time < max_time_seconds:
            neighbor_seq = current_sequence[:]
            
            mutation_type = random.random()
            
            if mutation_type < 0.6 and len(neighbor_seq) > 1:
                idx1, idx2 = random.sample(range(len(neighbor_seq)), 2)
                neighbor_seq[idx1], neighbor_seq[idx2] = neighbor_seq[idx2], neighbor_seq[idx1]
                
            elif mutation_type < 0.8:
                rand_order_idx = random.randint(0, len(neighbor_seq) - 1)
                random.shuffle(neighbor_seq[rand_order_idx])
                
            else:
                rand_order_idx = random.randint(0, len(neighbor_seq) - 1)
                if neighbor_seq[rand_order_idx]:
                    rand_item = random.choice(neighbor_seq[rand_order_idx])
                    if rand_item.can_rotate:
                        rand_item.force_rotation = not rand_item.force_rotation

            neighbor_layout = self.engine.pack_sequence(neighbor_seq, atomic=atomic)
            neighbor_fitness = self.get_fitness(neighbor_layout)

            if neighbor_fitness > current_fitness:
                current_sequence = neighbor_seq
                current_fitness = neighbor_fitness
                
                if current_fitness > best_fitness:
                    best_fitness = current_fitness
                    best_layout = neighbor_layout
            else:
                delta = current_fitness - neighbor_fitness
                try:
                    acceptance_prob = math.exp(-delta / temp)
                except OverflowError:
                    acceptance_prob = 0
                    
                if random.random() < acceptance_prob:
                    current_sequence = neighbor_seq
                    current_fitness = neighbor_fitness

            temp *= cooling_rate
            iterations += 1

            if temp < 0.01: 
                temp = 0.01

        
        return best_layout
