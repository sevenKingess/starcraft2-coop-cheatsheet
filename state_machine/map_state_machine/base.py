from PyQt5.QtCore import QStateMachine, QState, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QImage
from abc import abstractmethod
import logging  # 1. 导入logging模块
import cv2
import numpy as np


logger = logging.getLogger(__name__)
# 引入你之前定义的事件总线实例和全局事件枚举
from core.event_bus import EventBusInstance
from core.global_event_enums import GlobalEvents

# ==========================================
# 极简顺序状态机基类（带日志调试功能）
# ==========================================
class BaseSequentialStateMachine(QStateMachine):
    # 1. 内置状态切换信号（满足需求：next_state_trigger）
    next_state_trigger = pyqtSignal()

    def __init__(self, parent=None):
        # 注意：先初始化QObject，再初始化QStateMachine
        QObject.__init__(self, parent)
        QStateMachine.__init__(self, parent)

        self.red_label_img = cv2.imread("assets/red_label.png", cv2.IMREAD_UNCHANGED)
        self.green_label_img = cv2.imread("assets/green_label.png", cv2.IMREAD_UNCHANGED)
        self.red_point_img = cv2.imread("assets/red_point.png", cv2.IMREAD_UNCHANGED)

        self.green_label_img2 = cv2.imread("assets/green_label2.png", cv2.IMREAD_UNCHANGED)
        self.green_label_img3 = cv2.imread("assets/green_label3.png", cv2.IMREAD_UNCHANGED)

        self.gametime_timer = lambda: None
        self.tasktime_timer = lambda: None

        # 订阅事件
        EventBusInstance.subscribe(GlobalEvents.RES_GAMETIME_TIMER_START, self._get_gametime_timer)
        EventBusInstance.subscribe(GlobalEvents.RES_TASKTIME_TIMER_START, self._get_tasktime_timer)
        EventBusInstance.subscribe(GlobalEvents.RES_GAMETIME_TIMER_CALIBRATE, self._get_gametime_timer)
        EventBusInstance.subscribe(GlobalEvents.RES_TASKTIME_TIMER_CALIBRATE, self._get_tasktime_timer)
        EventBusInstance.subscribe(GlobalEvents.RES_TASKTIME_TIMER_STOP, self._get_tasktime_timer)
        EventBusInstance.subscribe(GlobalEvents.RES_TASKTIME_TIMER_PAUSE, self._get_tasktime_timer)

        # 2. 内置定时器（满足需求：self.timer = QTimer）
        self.timer = QTimer(self)
        self.timer.setInterval(1000)  # 默认100ms循环检测，可外部修改
        self.timer.setSingleShot(False)  # 周期性触发（循环调用）

        # 状态列表：存储所有通过add_sequential_state添加的状态
        self.state_list = []

        # 3. 调用抽象方法创建状态（用户必须重写该方法）
        self._init_states()

        # 自动绑定顺序状态转换（无需用户手动处理）
        self._bind_state_transitions()

        # 设置初始状态（默认第一个添加的状态）
        if self.state_list:
            self.setInitialState(self.state_list[0])

    def _get_gametime_timer(self, event):
        self.gametime_timer = lambda: TimeFormatter(event.get("time_closure")())

    def _get_tasktime_timer(self, event):
        if event.get("time_closure")() is None:
            self.tasktime_timer = lambda: TimeFormatter(0)
        else:
            self.tasktime_timer = lambda: TimeFormatter(event.get("time_closure")())

    # 主动请求游戏时间闭包
    def get_gametime_timer(self):
        EventBusInstance.publish(GlobalEvents.REQ_GAMETIME_TIMER_GETTIME)
        result = EventBusInstance.shared_data[GlobalEvents.RES_GAMETIME_TIMER_GETTIME]
        time_closure = result.get("time_closure")
        if time_closure() is None:
            return False
        self.gametime_timer = lambda: TimeFormatter(time_closure())
        return True
    
    # 主动请求任务时间闭包
    def get_tasktime_timer(self):
        EventBusInstance.publish(GlobalEvents.REQ_TASKTIME_TIMER_GETTIME)
        result = EventBusInstance.shared_data[GlobalEvents.RES_TASKTIME_TIMER_GETTIME]
        time_closure = result.get("time_closure")
        logger.debug(f"【_get_tasktime_timer】{time_closure()}")
        if time_closure() is None:
            return False
        self.tasktime_timer = lambda: TimeFormatter(time_closure())
        return True
    
    # 工具函数：输入时间字符串、浮点数秒、add=True，计算字符串时间
    def calculate_time_str(self, time_str: str, seconds: float, add: bool = True):  # 补充self参数（原代码遗漏）
        """
        工具函数：根据输入的时间字符串和秒数，计算新的时间字符串
        :param time_str: 输入时间字符串，支持格式：
                        1. 分:秒（如 "3:36"、"02:05"）
                        2. 时:分:秒（如 "1:20:30"、"01:02:03"）
                        3. 逗号分隔（如 "3,36" 自动转为 "3:36"）
        :param seconds: 要加减的浮点数秒数（如 10.5、-5.2，此处无需传负数，通过add控制加减）
        :param add: 是否为加法运算（True：时间 + seconds；False：时间 - seconds）
        :return: 格式化后的新时间字符串（无小时则返回 "mm:ss"，有小时则返回 "h:m:s"，补零保持两位）
        :raises ValueError: 输入时间字符串格式非法时抛出异常
        """
        try:
            # 1. 预处理：将逗号替换为冒号，统一格式解析
            time_str = time_str.replace(",", ":")
            # 按冒号分割时间部分，得到 [时, 分, 秒] 或 [分, 秒]
            time_parts = time_str.split(":")
            # 转换为浮点数，便于计算
            time_parts = [float(part) for part in time_parts]

            # 2. 解析时间字符串为总秒数
            total_seconds = 0.0
            if len(time_parts) == 2:
                # 格式：分:秒 → 总秒数 = 分*60 + 秒
                minutes, secs = time_parts
                total_seconds = minutes * 60 + secs
            elif len(time_parts) == 3:
                # 格式：时:分:秒 → 总秒数 = 时*3600 + 分*60 + 秒
                hours, minutes, secs = time_parts
                total_seconds = hours * 3600 + minutes * 60 + secs
            else:
                # 不支持的格式（非2段/3段）
                raise ValueError(f"不支持的时间格式：{time_str}，请使用 mm:ss 或 h:m:s 格式")

            # 3. 计算新的总秒数（控制加减，且保证总秒数不小于0）
            if add:
                new_total_seconds = total_seconds + seconds
            else:
                new_total_seconds = total_seconds - seconds
            # 边界处理：避免出现负时间
            new_total_seconds = max(0.0, new_total_seconds)

            # 4. 将新的总秒数转换为时、分、秒（取整，兼容业务场景；如需保留小数可调整）
            # 计算小时
            hours = int(new_total_seconds // 3600)
            remaining_sec = new_total_seconds % 3600
            # 计算分钟
            minutes = int(remaining_sec // 60)
            # 计算最终秒数
            final_secs = int(remaining_sec % 60)

            # 5. 格式化时间字符串（根据是否有小时，返回不同格式）
            if hours > 0:
                # 带小时：格式化为 h:mm:ss（分钟和秒补零为2位）
                new_time_str = f"{hours}:{minutes:02d}:{final_secs:02d}"
            else:
                # 无小时：格式化为 m:ss（分钟不补零，秒补零为2位，兼容你的业务格式如 "3:36"）
                new_time_str = f"{minutes}:{final_secs:02d}"

            return new_time_str

        except (ValueError, IndexError) as e:
            raise ValueError(f"解析或计算时间失败：{e}，输入时间字符串：{time_str}")
        
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
    
    # 工具函数：判断图片中指定位置范围内是否有红色像素
    def judge_red_in_img(self, img: QPixmap, x: float, y: float, color_range: float = 0.1) -> bool:
        # 转换为QImage格式（方便获取像素颜色）
        img_width = img.width()
        img_height = img.height()

        # 1. 计算目标位置的绝对坐标（相对坐标转绝对坐标）
        target_abs_x = x * img_width
        target_abs_y = y * img_height

        # 2. 计算检测范围的边界（基于偏移比例，限制在图片范围内，转整数像素坐标）
        offset_x = color_range * img_width
        offset_y = color_range * img_height
        min_x = max(0, int(target_abs_x - offset_x))
        max_x = min(img_width - 1, int(target_abs_x + offset_x))  # 防止越界（索引从0开始）
        min_y = max(0, int(target_abs_y - offset_y))
        max_y = min(img_height - 1, int(target_abs_y + offset_y))

        input_img = self.pixmap_to_cv2(img)[min_y:max_y, min_x:max_x]

        return self.is_template_in_image(input_img, self.red_point_img, threshold=0.8, scale_list=[0.5,0.6,0.7,0.8,0.9,1.0,1.1,1.2])

    def judge_green_label_in_img(self, img: QPixmap, x: float, y: float, color_range: float = 0.1) -> bool:
        img_width = img.width()
        img_height = img.height()

        # 1. 计算目标位置的绝对坐标（相对坐标转绝对坐标）
        target_abs_x = x * img_width
        target_abs_y = y * img_height

        # 2. 计算检测范围的边界（基于偏移比例，限制在图片范围内，转整数像素坐标）
        offset_x = color_range * img_width
        offset_y = color_range * img_height
        min_x = max(0, int(target_abs_x - offset_x))
        max_x = min(img_width - 1, int(target_abs_x + offset_x))  # 防止越界（索引从0开始）
        min_y = max(0, int(target_abs_y - offset_y))
        max_y = min(img_height - 1, int(target_abs_y + offset_y))

        input_img = self.pixmap_to_cv2(img)[min_y:max_y, min_x:max_x]

        return self.is_template_in_image(input_img, self.green_label_img, scale_list=[0.5,0.6,0.7,0.8,0.9,1.0,1.1])
        
    def judge_green_label2_in_img(self, img: QPixmap, x: float, y: float, color_range: float = 0.1) -> bool:
        img_width = img.width()
        img_height = img.height()

        # 1. 计算目标位置的绝对坐标（相对坐标转绝对坐标）
        target_abs_x = x * img_width
        target_abs_y = y * img_height

        # 2. 计算检测范围的边界（基于偏移比例，限制在图片范围内，转整数像素坐标）
        offset_x = color_range * img_width
        offset_y = color_range * img_height
        min_x = max(0, int(target_abs_x - offset_x))
        max_x = min(img_width - 1, int(target_abs_x + offset_x))  # 防止越界（索引从0开始）
        min_y = max(0, int(target_abs_y - offset_y))
        max_y = min(img_height - 1, int(target_abs_y + offset_y))

        input_img = self.pixmap_to_cv2(img)[min_y:max_y, min_x:max_x]

        return self.is_template_in_image(input_img, self.green_label_img2, scale_list=[0.8,0.9,1.0,1.1,1.2])
    
    def judge_green_label3_in_img(self, img: QPixmap, x: float, y: float, color_range: float = 0.15) -> bool:
        img_width = img.width()
        img_height = img.height()

        # 1. 计算目标位置的绝对坐标（相对坐标转绝对坐标）
        target_abs_x = x * img_width
        target_abs_y = y * img_height

        # 2. 计算检测范围的边界（基于偏移比例，限制在图片范围内，转整数像素坐标）
        offset_x = color_range * img_width
        offset_y = color_range * img_height
        min_x = max(0, int(target_abs_x - offset_x))
        max_x = min(img_width - 1, int(target_abs_x + offset_x))  # 防止越界（索引从0开始）
        min_y = max(0, int(target_abs_y - offset_y))
        max_y = min(img_height - 1, int(target_abs_y + offset_y))

        input_img = self.pixmap_to_cv2(img)[min_y:max_y, min_x:max_x]

        return self.is_template_in_image(input_img, self.green_label_img3, threshold=0.7, scale_list=[0.8,0.9,1.0,1.1,1.2])

    def judge_red_label_in_img(self, img: QPixmap, x: float, y: float, color_range: float = 0.1) -> bool:
        img_width = img.width()
        img_height = img.height()

        # 1. 计算目标位置的绝对坐标（相对坐标转绝对坐标）
        target_abs_x = x * img_width
        target_abs_y = y * img_height

        # 2. 计算检测范围的边界（基于偏移比例，限制在图片范围内，转整数像素坐标）
        offset_x = color_range * img_width
        offset_y = color_range * img_height
        min_x = max(0, int(target_abs_x - offset_x))
        max_x = min(img_width - 1, int(target_abs_x + offset_x))  # 防止越界（索引从0开始）
        min_y = max(0, int(target_abs_y - offset_y))
        max_y = min(img_height - 1, int(target_abs_y + offset_y))

        input_img = self.pixmap_to_cv2(img)[min_y:max_y, min_x:max_x]

        return self.is_template_in_image(input_img, self.red_label_img, threshold=0.75, scale_list=[0.5,0.6,0.7,0.8,0.9,1.0,1.1])

    def is_template_in_image(self, cropped_img, template_img, method=cv2.TM_CCOEFF_NORMED, threshold=0.75, scale_list=[0.5,0.6,0.7,0.8,0.9]):
        """
        新增Mask支持：处理带透明通道的模板，仅非透明区域参与匹配
        保留多比例缩放功能，任一缩放比例超阈值即返回匹配成功
        :param cropped_img: 截取后的图像
        :param template_img: 带Alpha通道的原始模板图像（4通道：BGR+Alpha）
        :param method: 匹配方法
        :param threshold: 相似度阈值
        :param scale_list: 模板缩放比例列表
        :return: 匹配结果（是否成功+最优匹配信息）
        """
        # -------------------------- 1. 提取模板和Mask（处理透明通道） --------------------------
        # 验证模板通道数，提取BGR通道和Alpha Mask
        if template_img.shape[-1] == 4:
            # 4通道（BGR+Alpha）：提取BGR通道作为模板图像，Alpha通道作为Mask
            template_bgr = template_img[:, :, :3]
            template_mask_original = template_img[:, :, 3]  # Alpha通道：0=透明，255=不透明
            # print("检测到模板透明通道，将使用Mask进行匹配")
        elif template_img.shape[-1] == 3:
            # 3通道（无透明）：不使用Mask，Mask设为全1（所有区域有效）
            template_bgr = template_img
            template_mask_original = np.ones(template_img.shape[:2], dtype=np.uint8) * 255
            # print("模板无透明通道，按常规方式匹配")
        else:
            raise ValueError(f"不支持的模板通道数：{template_img.shape[-1]}（仅支持3通道/4通道）")
        
        # 模板灰度转换（用于匹配）
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        original_template_h, original_template_w = template_gray.shape[:2]
        # 截取区域灰度转换
        cropped_gray = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
        cropped_h, cropped_w = cropped_gray.shape[:2]
        
        # -------------------------- 2. 初始化匹配结果 --------------------------
        is_match_success = False  # 是否匹配成功（任一缩放比例超阈值）

        # -------------------------- 3. 遍历缩放比例，执行带Mask的匹配 --------------------------
        for scale in scale_list:
            # 计算缩放后的模板尺寸（保持宽高比）
            scaled_w = int(original_template_w * scale)
            scaled_h = int(original_template_h * scale)
            
            # 跳过缩放后尺寸无效的情况
            if scaled_w <= 0 or scaled_h <= 0 or scaled_w > cropped_w or scaled_h > cropped_h:
                logger.debug(f"跳过缩放比例 {scale}：缩放后模板尺寸({scaled_w}x{scaled_h})无效")
                continue
            
            # 缩放模板（根据缩放方向选择最优插值方法）
            if scale < 1.0:
                # 缩小：INTER_AREA 插值精度更高
                scaled_template = cv2.resize(template_gray, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
                scaled_mask = cv2.resize(template_mask_original, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
            else:
                # 放大：INTER_CUBIC 插值细节更清晰
                scaled_template = cv2.resize(template_gray, (scaled_w, scaled_h), interpolation=cv2.INTER_CUBIC)
                scaled_mask = cv2.resize(template_mask_original, (scaled_w, scaled_h), interpolation=cv2.INTER_CUBIC)
            
            # 二值化Mask（确保透明区域为0，非透明区域为255，避免半透明干扰）
            _, scaled_mask_bin = cv2.threshold(scaled_mask, 127, 255, cv2.THRESH_BINARY)
            # 计算Mask有效区域面积（用于后续相似度校正，可选）
            mask_valid_area = np.count_nonzero(scaled_mask_bin)
            if mask_valid_area == 0:
                logger.debug(f"跳过缩放比例 {scale}：Mask无有效区域")
                continue

            # -------------------------- 4. 带Mask的模板匹配（核心修改） --------------------------
            # 执行基础模板匹配
            result = cv2.matchTemplate(cropped_gray, scaled_template, method)
            
            # 关键：使用Mask过滤，仅计算非透明区域的相似度（校正匹配结果）
            # 对于归一化匹配方法（TM_CCOEFF_NORMED），Mask可排除透明区域的干扰
            # 这里采用局部相似度校正，确保仅有效区域参与计算
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            # 确定当前缩放比例下的最佳相似度
            current_sim = max_val if method in [cv2.TM_CCOEFF, cv2.TM_CCOEFF_NORMED, cv2.TM_CCORR, cv2.TM_CCORR_NORMED] else min_val
            
            # -------------------------- 5. 更新匹配状态和最佳信息 --------------------------
            # 判断当前缩放比例是否匹配成功
            if current_sim >= threshold:
                is_match_success = True  # 任一缩放比例超阈值，标记为成功
                logger.debug(f"缩放比例 {scale}：匹配成功，相似度 {current_sim:.2f}（≥阈值 {threshold}）")
            else:
                logger.debug(f"缩放比例 {scale}：匹配失败，相似度 {current_sim:.2f}（<阈值 {threshold}）")

        return is_match_success

    # ==========================================
    # 必须被重写的抽象方法（满足需求：强制用户在此创建状态）
    # ==========================================
    @abstractmethod
    def _init_states(self):
        """
        抽象方法：必须在子类中重写！
        在此方法中调用 self.add_sequential_state(...) 创建所有状态
        """
        pass

    # ==========================================
    # 核心功能：增加新状态（新增state_name参数，添加日志输出）
    # 参数说明：
    # 1. map_process_table：地图流程表（退出状态时发布到事件总线）
    # 2. task_process_table：任务流程表（退出状态时发布到事件总线）
    # 3. point_on_minimap：小地图上的点（退出状态时发布到事件总线）
    # 4. check_func：lambda函数/普通函数，循环调用，返回True时触发下一个状态
    # 5. state_name：状态名称（可选，用于日志识别，默认自动生成「状态_索引」）
    # ==========================================
    def add_sequential_state(self, map_process_table=None, task_process_table=None,
                             point_on_minimap=None, check_func=None, state_name=None):
        # 默认check_func：返回False（不自动触发切换，用户可自定义）
        if check_func is None:
            def default_check():
                return False
            check_func = default_check

        # 创建当前状态
        current_state = QState(self)
        # 将状态添加到列表，用于后续自动绑定转换
        self.state_list.append(current_state)

        # 自动生成状态名称（若用户未指定）
        state_index = len(self.state_list) - 1  # 获取当前状态索引
        if state_name is None:
            state_name = f"状态_{state_index}"  # 默认名称：状态_0、状态_1...
        # 给QState对象设置名称属性（可选，便于后续调试）
        current_state.setProperty("state_name", state_name)

        # ==========================================
        # 自动处理：状态进入时 - 定时器绑定并启动 + 日志输出
        # ==========================================
        def on_state_enter():
            # 日志：记录状态进入（INFO级别，清晰可见）
            logger.info(f"【状态进入】{self.__class__.__name__} - {state_name}")
            # 先解绑定时器（避免重复绑定）
            if self.timer.receivers(self.timer.timeout) > 0:
                self.timer.timeout.disconnect()
            # 绑定定时器到检查函数的包装器
            self.timer.timeout.connect(lambda: self._check_and_trigger(check_func))
            # 启动定时器（开始循环调用check_func）
            self.timer.start()

        # ==========================================
        # 自动处理：状态退出时 - 定时器解绑+停止 + 发布流程表 + 日志输出
        # ==========================================
        def on_state_exit():
            # 日志：记录状态退出（INFO级别，清晰可见）
            logger.info(f"【状态退出】{self.__class__.__name__} - {state_name}")
            # 解绑定时器
            try:
                self.timer.timeout.disconnect()
            except (TypeError, RuntimeError):
                pass
            # 停止定时器
            self.timer.stop()
            # 发布地图流程表到事件总线
            if map_process_table is not None:
                if callable(map_process_table):
                    result = map_process_table()
                    if result is not None:
                        EventBusInstance.publish(GlobalEvents.REQ_MAPPROCESSTABLE_UPDATE, result)
                else:
                    EventBusInstance.publish(GlobalEvents.REQ_MAPPROCESSTABLE_UPDATE, map_process_table)
            # 发布任务流程表到事件总线
            if task_process_table is not None:
                if callable(task_process_table):
                    result = task_process_table()
                    if result is not None:
                        EventBusInstance.publish(GlobalEvents.REQ_TASKPROCESSTABLE_UPDATE, result)
                else:
                    EventBusInstance.publish(GlobalEvents.REQ_TASKPROCESSTABLE_UPDATE, task_process_table)
            # 发布小地图重绘制到事件总线
            if point_on_minimap is not None:
                if callable(point_on_minimap):
                    result = point_on_minimap()
                    if result is not None:
                        EventBusInstance.publish(GlobalEvents.REQ_MINIMAP_REPAINT, result)
                else:
                    EventBusInstance.publish(GlobalEvents.REQ_MINIMAP_REPAINT, point_on_minimap)

        # 绑定状态的进入和退出信号
        current_state.entered.connect(on_state_enter)
        current_state.exited.connect(on_state_exit)

    # ==========================================
    # 内部私有方法：检查函数返回值并触发状态切换
    # ==========================================
    def _check_and_trigger(self, check_func):
        try:
            # 调用用户传入的检查函数
            is_finished = check_func()
            # 如果返回True，触发下一个状态
            if is_finished:
                logger.debug(f"【状态切换触发】检查函数返回True，即将切换到下一个状态")  # DEBUG级别，详细调试
                self.next_state_trigger.emit()
        except Exception as e:
            logger.error(f"【状态检查异常】检查函数执行失败：{e}", exc_info=True)  # ERROR级别，记录异常堆栈
            self.timer.stop()

    # ==========================================
    # 内部私有方法：自动绑定顺序状态转换
    # ==========================================
    def _bind_state_transitions(self):
        # 遍历状态列表，为相邻状态绑定转换（通过next_state_trigger信号）
        for i in range(len(self.state_list) - 1):
            current_state = self.state_list[i]
            next_state = self.state_list[i + 1]
            # 绑定：当前状态下，发射next_state_trigger信号则跳转到下一个状态
            current_state.addTransition(self.next_state_trigger, next_state)


class TimeFormatter:
    def __init__(self, total_seconds: float):
        """
        初始化：接收总秒数（float类型），转换为分钟和秒
        :param total_seconds: 总秒数（如7.0、67.5、120.0等）
        """
        # 存储原始总秒数（用于比较大小，核心依据）
        self.total_seconds = float(total_seconds)
        # 计算分钟和秒
        self.minute = int(self.total_seconds // 60)  # 取整数部分作为分钟
        self.second = self.total_seconds % 60        # 取余数作为秒（保留小数）

    def __str__(self) -> str:
        """
        转换为「分钟:秒」格式的字符串（核心格式化功能）
        - 示例：7.0 → "0:7"、67.0 → "1:7"、67.5 → "1:7.5"、120.0 → "2:0"
        """
        # 处理秒数的显示：显示为整数
        second_str = str(int(self.second))
        return f"{self.minute}:{second_str}"

    def __repr__(self) -> str:
        """调试时显示的格式，方便开发排查"""
        return f"TimeFormatter(total_seconds={self.total_seconds}, str={str(self)})"

    # 辅助方法：解析「分钟:秒」格式字符串为总秒数
    def _parse_time_str(self, time_str: str) -> float:
        """
        解析 "m:s" 格式字符串为总秒数，用于比较大小
        :param time_str: 分:秒格式字符串（如"0:7"、"1:7.5"、"2:0"）
        :return: 总秒数
        """
        try:
            # 按冒号分割，获取分钟和秒
            minute_part, second_part = time_str.split(":")
            # 转换为数字
            minute = float(minute_part)
            second = float(second_part)
            # 计算总秒数
            return minute * 60 + second
        except (ValueError, IndexError) as e:
            # 处理无效格式（如"1:7:8"、"abc"、"1"等）
            raise TypeError(f"无效的时间字符串格式：{time_str}，请使用「分钟:秒」格式（如'1:7'）") from e

    # 重载比较魔法方法：实现与字符串/同类实例的正确比较
    def __gt__(self, other) -> bool:
        """大于（>）：self > other"""
        # 1. 处理同类实例比较
        if isinstance(other, TimeFormatter):
            return self.total_seconds > other.total_seconds
        # 2. 处理字符串比较（核心需求）
        elif isinstance(other, str):
            other_total = self._parse_time_str(other)
            return self.total_seconds > other_total
        # 3. 处理其他类型
        else:
            raise TypeError(f"不支持与{type(other)}类型比较，请使用TimeFormatter实例或「分钟:秒」格式字符串")

    def __lt__(self, other) -> bool:
        """小于（<）：self < other"""
        if isinstance(other, TimeFormatter):
            return self.total_seconds < other.total_seconds
        elif isinstance(other, str):
            other_total = self._parse_time_str(other)
            return self.total_seconds < other_total
        else:
            raise TypeError(f"不支持与{type(other)}类型比较")

    def __eq__(self, other) -> bool:
        """等于（==）：self == other"""
        if isinstance(other, TimeFormatter):
            return self.total_seconds == other.total_seconds
        elif isinstance(other, str):
            other_total = self._parse_time_str(other)
            return self.total_seconds == other_total
        else:
            raise TypeError(f"不支持与{type(other)}类型比较")

    def __ge__(self, other) -> bool:
        """大于等于（>=）：self >= other"""
        return self.__gt__(other) or self.__eq__(other)

    def __le__(self, other) -> bool:
        """小于等于（<=）：self <= other"""
        return self.__lt__(other) or self.__eq__(other)