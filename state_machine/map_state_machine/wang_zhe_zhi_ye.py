from PyQt5.QtCore import QStateMachine, QState, QSignalTransition, pyqtSignal, pyqtSlot
from state_machine.map_state_machine.base import BaseSequentialStateMachine
from core.event_bus import EventBusInstance
from core.global_event_enums import GlobalEvents

import logging
logger = logging.getLogger(__name__)

class WangZheZhiYe(BaseSequentialStateMachine):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.type = None

    def _init_states(self):
        _RED_POINTS = {
            "A" : (0.04, 0.65),
            "B" : (0.555, 0.07),
            "C" : (0.96, 0.02),
            "D" : (0.96, 0.74)
        }

        map_process_table = [
            ("00:30", "圈养神器:第一个3*3建筑放在感应塔正上方（左右各留出1格），3*3建筑右边下两格的右边2*2就是神器位置"),
            ("14:00", "红点A/C"),
            ("21:30", "红点B/C/D"),
            ("29:00", "红点A/B/C/D"),
            ("36:30", "红点A/B/C/D"),
            ("44:15", "红点A/B/C/D"),
        ]
        point_on_minimap = [
            ("A", *_RED_POINTS["A"]),
            ("B", *_RED_POINTS["B"]),
            ("C", *_RED_POINTS["C"]),
            ("D", *_RED_POINTS["D"]),
        ]

        def check_func():
            return True

        self.add_sequential_state(
            map_process_table=map_process_table,
            point_on_minimap=point_on_minimap,
            check_func=check_func
        )

        # =====================================
        # 最终状态等待外部状态机切换
        # =====================================

        self.add_sequential_state(
            check_func= lambda: False
        )