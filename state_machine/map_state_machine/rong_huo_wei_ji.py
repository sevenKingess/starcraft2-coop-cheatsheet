from PyQt5.QtGui import QPixmap, QImage
import numpy as np
import cv2
from state_machine.map_state_machine.base import BaseSequentialStateMachine
from core.event_bus import EventBusInstance
from core.global_event_enums import GlobalEvents

import logging
logger = logging.getLogger(__name__)

import easyocr
class RongHuoWeiJiOCRReader:
    def __init__(self):
        try:
            self.reader = easyocr.Reader(['ch_sim'], gpu=True)
        except Exception as e:
            self.reader = easyocr.Reader(['ch_sim'], gpu=False)

        self.target_txts = [
            "岩浆潮来得快去得也快",
            "岩浆好像完全消退",
            "岩浆又消退",
            "岩浆潮快要退",
            "这波爆发应该是彻底结束了",
            "有消息说岩浆正在下沉",
            "这场喷发应该暂时结束了",
            "岩浆消退",
            "退去的岩浆",
            "我认为水晶"
        ]

    def read(self, img):
        img = self.pixmap_to_cv2(img)
        results = self.reader.readtext(img, detail=0)
        logger.debug(f"【熔火危机】OCR识别结果: {results}")
        for target_txt in self.target_txts:
            for result in results:
                if target_txt in result:
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

class RongHuoWeiJi(BaseSequentialStateMachine):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.ocr_reader = RongHuoWeiJiOCRReader()

        self.begin_time = None
        self.mid_time = None
        self.end_time = None

    def _calc_next_time_window(self, time1:str, time2: int, time3: int):
        '''
        当前岩浆褪去时间(time1) + 下次爆发间隔(time2) + 持续时间(time3) +25（end）/-20(begin)
        '''
        begin_time = self.calculate_time_str(time1, time2+time3-20, add=True)
        mid_time = self.calculate_time_str(time1, time2+time3-5, add=True)
        end_time = self.calculate_time_str(time1, time2+time3+20, add=True)
        return begin_time, mid_time, end_time

    def _init_states(self):
        _RED_POINTS = {
            "A" : (0.105, 0.53),
            "B" : (0.89, 0.12),
            "C" : (0.56, 0.87),
            "D" : (0.93, 0.83)
        }

        # 岩浆波次n后的水晶位置
        _SHUIJING_POINTS = {
            "1" : [],
            "2" : [],
            "3" : [
                ("1", 0.2, 0.42),
                ("2", 0.57, 0.4),
            ],
            "4" : [
                ("1", 0.15, 0.65),
                ("2", 0.2, 0.2),
                ("3", 0.58, 0.1),
            ],
            "5" : [
                ("1", 0.18, 0.82),
                ("2", 0.28, 0.65),
                ("3", 0.62, 0.4),
                ("4", 0.62, 0.15),
            ],
            "6" : [
                ("1", 0.85, 0.15),
                ("2", 0.82, 0.6),
                ("3", 0.7, 0.67),
            ],
            "7" : [
                ("1", 0.85, 0.15),
                ("2", 0.85, 0.3),
                ("3", 0.9, 0.85),
            ],
            "8" : [
                ("1", 0.64, 0.86),
                ("2", 0.79, 0.68),
                ("3", 0.9, 0.85),
            ],
            "9" : [
                ("1", 0.3, 0.68),
                ("2", 0.9, 0.85),
            ],
        }


        self.map_process_table = [
            ("3:30", "红点"),
            ("6:00", "红点"),
            ("9:00", "红点（1分半误差）"),
            ("12:00", "红点（1分半误差）"),
            ("15:00", "红点（1分半误差）"),
            ("18:00", "红点（1分半误差）"),
            ("21:00", "红点（1分半误差）"),
            ("24:00", "红点（1分半误差）"),
            ("27:00", "红点（1分半误差）"),
            ("29:00", "红点（1分半误差）"),
            ("31:00", "红点（1分半误差）"),
            ("32:00", "红点（1分半误差）"),
            ("0:30", "圈养神器：左下角基地对角线数一个基地，贴着上面向右露出一格放3*3，3*3右边上两个右方的2*2就是神器位置"),
        ]
        self.point_on_minimap = [
            ("A", *_RED_POINTS["A"]),
            ("B", *_RED_POINTS["B"]),
            ("C", *_RED_POINTS["C"]),
            ("D", *_RED_POINTS["D"]),
        ]

        # =====================================
        # 开局播报第一波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            # 发布检测下一次岩浆的时间窗口
            self.begin_time = "2:10"
            self.end_time = "2:25"
            return True

        self.add_sequential_state(
            map_process_table=self.map_process_table + [("1:30", "岩浆升起")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["1"],
            check_func=check_func
        )

        # =====================================
        # 检测到第一波岩浆退去后，播报第二波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第一波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第一波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 90, 15)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["2"],
            check_func=check_func
        )

        # =====================================
        # 检测到第二波岩浆退去后，播报第三波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第二波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第二波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 150, 30)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["3"],
            check_func=check_func
        )

        # =====================================
        # 检测到第三波岩浆退去后，播报第四波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第三波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第三波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 210, 30)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time

                    self.map_process_table += [(self.mid_time, "奖励")]
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["4"],
            check_func=check_func
        )

        # =====================================
        # 检测到第四波岩浆退去后，播报第五波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第四波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第四波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 150, 30)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["5"],
            check_func=check_func
        )

        # =====================================
        # 检测到第五波岩浆退去后，播报第六波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第五波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第五波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 210, 30)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["6"],
            check_func=check_func
        )

        # =====================================
        # 检测到第六波岩浆退去后，播报第七波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第六波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第六波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 150, 30)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["7"],
            check_func=check_func
        )

        # =====================================
        # 检测到第七波岩浆退去后，播报第八波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第七波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第七波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 210, 30)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["8"],
            check_func=check_func
        )

        # =====================================
        # 检测到第八波岩浆退去后，播报第九波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第八波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第八波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 150, 30)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["9"],
            check_func=check_func
        )

        # =====================================
        # 检测到第九波岩浆退去后，播报第十波岩浆时间和之后的水晶位置
        # =====================================

        def check_func():
            if self.gametime_timer() >= self.end_time:
                logger.info(f"未检测到检测到第九波岩浆退去，直接进入下一状态")
                # self.mid_time = ""
                return True
            elif self.begin_time <= self.gametime_timer() < self.end_time:
                EventBusInstance.publish(GlobalEvents.REQ_CHAT_SCREENSHOT)
                chat_screenshot, _ = EventBusInstance.shared_data[GlobalEvents.RES_CHAT_SCREENSHOT]
                if self.ocr_reader.read(chat_screenshot):
                    logger.info(f"检测到第九波岩浆退去，进入下一状态")
                    # 发布检测下一次岩浆的时间窗口
                    # 当前岩浆褪去时间 + 下次爆发间隔 + 持续时间 +20（end）/-20(begin)
                    begin_time, mid_time, end_time = self._calc_next_time_window(str(self.gametime_timer()), 120, 30)
                    self.begin_time = begin_time
                    self.mid_time = mid_time
                    self.end_time = end_time
                    return True
            return False

        self.add_sequential_state(
            map_process_table=lambda: self.map_process_table + [(self.mid_time, "岩浆升起\n(20秒误差)")],
            point_on_minimap=self.point_on_minimap + _SHUIJING_POINTS["9"],
            check_func=check_func
        )

        # =====================================
        # 之后是完全重复，需要就复制就行
        # =====================================

        # =====================================
        # 最终状态等待外部状态机切换
        # =====================================

        self.add_sequential_state(
            check_func= lambda: False
        )