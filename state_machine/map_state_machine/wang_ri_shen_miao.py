from PyQt5.QtCore import QStateMachine, QState, QSignalTransition, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QPixmap
import cv2
import numpy as np
from state_machine.map_state_machine.base import BaseSequentialStateMachine
from core.event_bus import EventBusInstance
from core.global_event_enums import GlobalEvents

import logging
logger = logging.getLogger(__name__)


import easyocr
class WangRiShenMiaoOCRReader:
    def __init__(self):
        try:
            self.reader = easyocr.Reader(['ch_sim'], gpu=True)
        except Exception as e:
            self.reader = easyocr.Reader(['ch_sim'], gpu=False)

        self.target_txts = [
            "雷诺",
            "莎拉凯瑞甘",
            "阿塔尼斯",
            "斯旺",
            "扎加拉",
            "沃拉尊",
            "凯拉克斯",
            "阿巴瑟",
            "阿拉纳克",
            "诺娃",
            "斯托科夫",
            "菲尼克斯",
            "德哈卡",
            "霍纳",
            "汉",
            "泰凯斯",
            "泽拉图",
            "阿克图尔斯蒙斯克",
            "斯台特曼"
        ]

        self.allow_txts = "".join(self.target_txts)

    def read_chat(self, img):
        img = self.pixmap_to_cv2(img)
        results = self.reader.readtext(img, detail=0, allowlist=self.allow_txts)
        logger.debug(f"【往日神庙】OCR识别结果: {results}")
        for result in results:
            for target_txt in self.target_txts:
                if result.startswith(target_txt):
                    return True
        return False

    def pixmap_to_cv2(self, pixmap: QPixmap):
        """
        将QPixmap转换为cv2可用的BGR格式数组
        修复点：
        1. 自动适配RGBA/RGB/灰度图格式
        2. 校验数组尺寸匹配性
        3. 增加异常处理
        """
        try:
            # 1. 获取Pixmap的真实尺寸（避免缩放/错误赋值）
            width = pixmap.width()
            height = pixmap.height()
            # print(f"Pixmap真实尺寸：宽={width}, 高={height}")  # 调试用，可后续删除
            
            # 2. 将Pixmap转换为QImage，获取像素数据
            q_image = pixmap.toImage()
            # 确保QImage是连续的内存布局
            q_image = q_image.convertToFormat(4)  # QImage.Format_RGB32 (对应RGBA)
            
            # 3. 读取像素数据
            ptr = q_image.bits()
            ptr.setsize(q_image.byteCount())
            # 读取为一维数组
            img_array = np.frombuffer(ptr, np.uint8)
            
            # 4. 自动判断通道数并重塑
            total_pixels = width * height
            channel_count = img_array.size // total_pixels  # 计算实际通道数
            # print(f"实际通道数：{channel_count}")  # 调试用，可后续删除
            
            # 5. 按实际通道数重塑
            if channel_count == 4:
                # RGBA格式 → 先重塑，再去掉Alpha通道
                rgba_array = img_array.reshape((height, width, 4))
                rgb_array = rgba_array[:, :, :3]  # 保留RGB，丢弃Alpha
            elif channel_count == 3:
                # 纯RGB格式
                rgb_array = img_array.reshape((height, width, 3))
            elif channel_count == 1:
                # 灰度图 → 转换为RGB（cv2兼容）
                gray_array = img_array.reshape((height, width))
                rgb_array = cv2.cvtColor(gray_array, cv2.COLOR_GRAY2RGB)
            else:
                raise ValueError(f"不支持的通道数：{channel_count}")
            
            # 6. RGB转BGR（cv2默认格式）
            cv2_img = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
            return cv2_img
            
        except Exception as e:
            logger.error(f"Pixmap转CV2失败：{str(e)}")
            # 可选：返回空图或抛出异常，根据业务调整
            raise  # 也可改为 return None

class WangRiShenMiao(BaseSequentialStateMachine):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.type = None
        self.typeB = None
        self.ocr_reader = WangRiShenMiaoOCRReader()

    def _init_states(self):
        _RED_POINTS = {
            "A" : (0.11, 0.91),
            "a" : (0.19, 0.79),
            "B" : (0.1,0.05),
            "b" : (0.23, 0.16),
            "C" : (0.9, 0.07),
            "c" : (0.83, 0.17),
            "D" : (0.9,0.9),
            "d" : (0.83, 0.795),

            # 空投点位
            "1" : (0.47,0.53),
            "2" : (0.59,0.52),
            "3" : (0.63,0.35),
        }

        self.map_process_table = [
            ("3:00", "红点A"),
            ("3:10", "（或者）红点A集结完毕"),
            ("3:15", "（或者）红点A集结完毕"),
        ]

        self.point_on_minimap = [
            ("A", *_RED_POINTS["A"]),
            ("a", *_RED_POINTS["a"]),
            ("B", *_RED_POINTS["B"]),
            ("b", *_RED_POINTS["b"]),
            ("C", *_RED_POINTS["C"]),
            ("c", *_RED_POINTS["c"]),
            ("D", *_RED_POINTS["D"]),
            ("d", *_RED_POINTS["d"]),
        ]


        def check_func():
            return True

        self.add_sequential_state(
            map_process_table=self.map_process_table,
            point_on_minimap=self.point_on_minimap,
            check_func=check_func
        )

        # =====================================
        # 在<=3：10和<3：15判断对话框是否出现
        # =====================================
        def map_process_table_func():
            result = [("3:30", "遭遇严重失误，波形判断失败")]
            if self.type == "A":
                result = [
                    ("3:00", "红点A"),
                    # ("3:15", "集结a"),

                    ("4:15", "红点A"),
                    # ("4:45", "集结a"),

                    ("6:00", "红点A"),
                    # ("6:20", "集结a"),

                    ("6:45", "红点A"),
                    # ("7:00", "集结a"),

                    ("7:30", "红点A"),
                    # ("7:45", "集结a"),

                    ("8:15", "虚空撕裂者-左下"),

                    ("9:00", "红点B"),
                    # ("9:15", "集结b"),
                    ("9:00", "红点D"),
                    # ("9:15", "集结d"),

                    ("10:00", "红点B"),
                    # ("10:20", "集结b"),
                    # ("10:00", "红点D"),
                    # ("10:20", "集结d"),

                    ("11:00", "红点B"),
                    # ("11:20", "集结b"),
                    ("11:00", "红点D"),
                    # ("11:20", "集结d"),

                    ("12:00", "红点A"),
                    # ("12:20", "集结a"),

                    ("12:30", "红点A"),
                    # ("12:50", "集结a"),

                    ("13:15", "红点A"),
                    # ("13:35", "集结a"),

                    ("13:45", "虚空撕裂者-右下"),

                    ("15:00", "红点C"),
                    # ("15:03", "集结c"),

                    ("15:20", "红点C"),
                    # ("15:25", "集结c"),

                    ("16:10", "空投3"),
                    ("16:40", "空投3"),

                    ("16:55", "虚空撕裂者-左上"),

                    ("18:00", "红点B"),
                    # ("18:20", "集结b"),

                    ("18:15", "红点D"),
                    # ("18:20", "集结d"),

                    ("19:15", "红点C"),
                    # ("19:35", "集结c"),

                    ("20:00", "红点A"),
                    # ("20:15", "集结a"),

                    ("20:15", "空投1"),
                    ("20:45", "空投2"),
                    ("21:15", "空投3"),
                    ("21:30", "空投1/2/3"),
                    ("21:30", "空投1/2/3"),

                    ("22:00", "红点A"),
                    # ("22:15", "集结a"),

                    ("22:30", "虚空撕裂者-左上"),
                    ("22:30", "虚空撕裂者-右下"),
                    ("22:30", "红点B"),
                    ("22:30", "红点D"),
                    # ("22:45", "集结b"),
                    # ("22:45", "集结d"),

                    ("23:30", "红点B"),
                    # ("23:45", "集结b"),

                    ("23:40", "红点D"),
                    # ("23:55", "集结d"),

                    ("24:40", "红点A"),
                    # ("24:55", "集结a"),
                    ("24:40", "红点B"),
                    # ("24:55", "集结b"),
                    ("24:40", "红点D"),
                    # ("24:55", "集结d"),

                ]
            elif self.type == "B":
                result = [
                    # 第一波校对
                    ("9:00", "红点B/D"), #0
                    # ("9:10", "集结b/d"),
                    # ("9:20", "集结b/d"),

                    ("11:00", "红点D/B"), #1
                    # ("11:15", "集结d/b"),
                    # ("11:20", "集结d/b"),

                    # 第二波校对
                    ("18:00", "红点B/A"),#2
                    # ("18:20", "集结a/b"),

                    ("18:15", "红点D/A"),#3
                    # ("18:45", "集结d/a"),


                    ("3:00", "红点A"),
                    # ("3:10", "集结a"),

                    ("4:10", "红点A"),
                    # ("4:40", "集结a"),

                    ("6:00", "红点A"),
                    # ("6:20", "集结a"),

                    ("6:45", "红点A"),
                    # ("7:00", "集结a"),

                    ("7:30", "红点A"),
                    # ("7:45", "集结a"),

                    ("8:15", "虚空撕裂者-左下"),


                    ("10:00", "红点B"),
                    # ("10:20", "集结b"),
                    ("10:00", "红点D"),
                    # ("10:20", "集结d"),

                    ("12:00", "红点A"),
                    # ("12:20", "集结a"),

                    ("12:30", "红点A"),
                    # ("12:50", "集结a"),

                    ("13:35", "红点D"),
                    # ("13:55", "集结d"),

                    ("13:45", "虚空撕裂者-右下"),

                    ("15:00", "空投3"),
                    ("15:30", "空投3"),

                    ("15:45", "虚空撕裂者-左上"),

                    ("16:35", "红点C"),
                    # ("16:38", "集结c"),
                    ("16:55", "红点C"),
                    # ("17:00", "集结c"),

                    ("19:15", "红点C"),
                    # ("19:35", "集结c"),

                    ("20:00", "虚空撕裂者-左下"),
                    ("20:00", "红点A"),
                    # ("20:20", "集结a"),

                    ("20:20", "红点C"),
                    # ("20:35", "集结c"),
                    ("20:40", "红点C"),
                    # ("20:50", "集结c"),


                    ("22:30", "虚空撕裂者-左上"),
                    ("22:30", "虚空撕裂者-右下"),
                    ("22:30", "红点B"),
                    ("22:30", "红点D"),
                    # ("22:45", "集结b"),
                    # ("22:45", "集结d"),

                    ("23:30", "红点B"),
                    # ("23:45", "集结b"),

                    ("23:40", "红点D"),
                    # ("23:55", "集结d"),

                    ("24:40", "红点A"),
                    # ("24:55", "集结a"),
                    ("24:40", "红点B"),
                    # ("24:55", "集结b"),
                    ("24:40", "红点D"),
                    # ("24:55", "集结d"),
                ]
                self.map_process_table = result.copy()
            return result

        def point_on_minimap_func():
            result = []
            if self.type == "A":
                result = [
                    ("1", *_RED_POINTS["1"]),
                    ("2", *_RED_POINTS["2"]),
                    ("3", *_RED_POINTS["3"])
                ]
            elif self.type == "B":
                result = [
                    ("3", *_RED_POINTS["3"])
                ]
            return self.point_on_minimap + result


        def check_func():
            if "3:15" > self.gametime_timer() >= "3:10":
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read_chat(chat_screenshot):
                    self.type = "B"
                    logger.debug("【往日神庙】波形判断为B")
                    return True
            if "3:20" >= self.gametime_timer() > "3:16":
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read_chat(chat_screenshot):
                    self.type = "A"
                    logger.debug("【往日神庙】波形判断为A")
                    return True
            if self.gametime_timer() > "3:20":
                self.type = None
                logger.debug("【往日神庙】波形判断为A")
                return True
            return False

        self.add_sequential_state(
            map_process_table=map_process_table_func,
            point_on_minimap=point_on_minimap_func,
            check_func=check_func
        )

        # =====================================
        # 如果是B类型要执行两次判断，这里执行第一次判断
        # =====================================

        def map_process_table_func():
            if self.type == "B":
                if self.typeB == "B":
                    new_list = [
                        ("9:00", "红点B"), #0
                        # ("9:10", "集结b"), #1
                        # ("9:20", "集结b"), #2

                        ("11:00", "红点D"), #3
                        # ("11:15", "集结d"), #4
                        # ("11:20", "集结d"), #5
                    ]
                    for idx in [0, 1]:
                        self.map_process_table[idx] = new_list[idx]
                elif self.typeB == "D":
                    new_list = [
                        ("9:00", "红点D"), #0
                        # ("9:10", "集结d"), #1
                        # ("9:20", "集结d"), #2

                        ("11:00", "红点B"), #3
                        # ("11:15", "集结b"), #4
                        # ("11:20", "集结b"), #5
                    ]
                    for idx in [0, 1]:
                        self.map_process_table[idx] = new_list[idx]
            return None

        def check_func():
            if self.type == "A":
                self.typeB = None
                return True
            elif self.type == "B":
                if self.gametime_timer() >= "9:30":
                    self.typeB = None
                    logger.debug("【往日神庙】第一波待判断红点未发现")
                    return True
                if "9:30" > self.gametime_timer() >= "9:00":
                    EventBusInstance.publish(GlobalEvents.REQ_MINIMAP_SCREENSHOT)
                    mini_map_pixmap = EventBusInstance.shared_data[GlobalEvents.RES_MINIMAP_SCREENSHOT]
                    result_B = self.judge_red_in_img(mini_map_pixmap, *_RED_POINTS["B"]) or self.judge_red_in_img(mini_map_pixmap, *_RED_POINTS["b"])
                    result_D = self.judge_red_in_img(mini_map_pixmap, *_RED_POINTS["D"]) or self.judge_red_in_img(mini_map_pixmap, *_RED_POINTS["d"])
                    if result_B and not result_D:
                        self.typeB = "B"
                        logger.debug("【往日神庙】第一波待判断红点为B")
                        return True
                    elif result_D and not result_B:
                        self.typeB = "D"
                        logger.debug("【往日神庙】第一波待判断红点为D")
                        return True
                    else:
                        logger.debug(f"【往日神庙】第一波待判断红点结果为result_B={result_B}, result_D={result_D}")
                return False

        self.add_sequential_state(
            map_process_table=map_process_table_func,
            check_func=check_func
        )

        # =====================================
        # 如果是B类型要执行两次判断，这里执行第二次判断
        # =====================================

        def map_process_table_func():
            if self.type == "B":
                if self.typeB == "A":
                    new_list = [
                        ("18:00", "红点B"),#6
                        # ("18:20", "集结a"),#7
                        ("18:15", "红点D"),#8
                        # ("18:45", "集结d"),#9
                    ]
                    for i, idx in enumerate([2, 3]):
                        self.map_process_table[idx] = new_list[i]
                elif self.typeB == "B":
                    new_list = [
                        ("18:00", "红点A"),#6
                        # ("18:20", "集结b"),#7
                        ("18:15", "红点A"),#8
                        # ("18:45", "集结a"),#9
                    ]
                    for i, idx in enumerate([2, 3]):
                        self.map_process_table[idx] = new_list[i]
                return self.map_process_table

        def check_func():
            if self.type == "A":
                self.typeB = None
                return True
            elif self.type == "B":
                if self.gametime_timer() >= "18:30":
                    self.typeB = None
                    logger.debug("【往日神庙】第二波待判断红点未发现")
                    return True
                if "18:30" > self.gametime_timer() >= "18:00":
                    EventBusInstance.publish(GlobalEvents.REQ_MINIMAP_SCREENSHOT)
                    mini_map_pixmap = EventBusInstance.shared_data[GlobalEvents.RES_MINIMAP_SCREENSHOT]
                    result_B = self.judge_red_in_img(mini_map_pixmap, *_RED_POINTS["B"]) or self.judge_red_in_img(mini_map_pixmap, *_RED_POINTS["b"])
                    result_A = self.judge_red_in_img(mini_map_pixmap, *_RED_POINTS["A"]) or self.judge_red_in_img(mini_map_pixmap, *_RED_POINTS["a"])
                    if result_A and not result_B:
                        self.typeB = "B"
                        logger.debug("【往日神庙】第二波待判断红点为A")
                        return True
                    elif result_B and not result_A:
                        self.typeB = "A"
                        logger.debug("【往日神庙】第二波待判断红点为B")
                        return True
                    else:
                        logger.debug(f"【往日神庙】第二波待判断红点结果为result_B={result_B}, result_A={result_A}")
                return False

        self.add_sequential_state(
            map_process_table=map_process_table_func,
            check_func=check_func
        )


        # =====================================
        # 最终状态等待外部状态机切换
        # =====================================

        self.add_sequential_state(
            check_func= lambda: False
        )