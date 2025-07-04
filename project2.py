
import os
import sqlite3
from datetime import datetime, timedelta
from openai import OpenAI
from typing import List, Dict, Tuple, Optional, Any, cast
from dataclasses import dataclass, field
import logging
import re
import time
import socket
import requests



# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-ae720db128ed441a979b7274b0f01538")

# 数据库配置
DB_NAME = "study_planner.db"

# 新增每日计划数据结构
@dataclass
class DailyPlan:
    day_number: int
    core_knowledge: str
    tasks: List[str] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)
    duration: str = ""
    assessment: str = ""

# ✅ 预设优质资源池
PRESET_RESOURCES = {
    "python": [
        {
            "title": "Python全套教程（超详细）",
            "url": "https://www.bilibili.com/video/BV1qW4y1a7fU/?spm_id_from=333.337.search-card.all.click&vd_source=21caed9bc6b79512b12020a7dd2d7176",
            "platform": "B站"
        }
    ],
    "人工智能": [
        {
            "title": "人工智能通识课",
            "url": "https://www.bilibili.com/video/BV1VZMLzMEUY/?spm_id_from=333.337.search-card.all.click&vd_source=21caed9bc6b79512b12020a7dd2d7176",
            "platform": "B站"
        }
    ],
    "信号与系统": [
        {
            "title": "信号与系统（清华）",
            "url": "https://www.bilibili.com/video/BV1g94y1Q76G/?spm_id_from=333.337.search-card.all.click",
            "platform": "B站"
        }
    ],
    "c++": [
        {
            "title": "C++从入门到精通",
            "url": "https://www.bilibili.com/video/BV1et411b73Z/?spm_id_from=333.337.search-card.all.click",
            "platform": "B站"
        }
    ],
    "c": [
        {
            "title": "C语言全套课程",
            "url": "https://www.bilibili.com/video/BV1Vm4y1r7jY/?spm_id_from=333.337.search-card.all.click",
            "platform": "B站"
        }
    ]
}


# 修改StudyPlan类，添加daily_plans属性
@dataclass
class StudyPlan:
    id: int
    user_id: int
    subject: str
    duration_days: int
    target_level: str
    content: str  # 原始Markdown内容
    created_at: str
    status: str = "active"
    progress: float = 0.0
    last_updated: Optional[str] = None
    daily_plans: List[DailyPlan] = field(default_factory=list)  # 解析后的每日计划

    def parse_daily_plans(self):
        """解析Markdown内容生成每日计划数据结构"""
        daily_pattern = re.compile(
            r'### 第(\d+)天\n- 核心知识点：(.*?)\n- 学习任务：\n(.*?)\n- 推荐资源：\n(.*?)\n- 预计时长：(.*?)\n- 评估方法：(.*?)(?=### 第|$)', 
            re.DOTALL
        )
        matches = daily_pattern.findall(self.content)
        
        for day_num_str, core, tasks_str, resources_str, duration, assessment in matches:
            day_num = int(day_num_str)
            daily_plan = DailyPlan(
                day_number=day_num,
                core_knowledge=core.strip(),
                duration=duration.strip(),
                assessment=assessment.strip()
            )
            
            # 解析任务列表
            daily_plan.tasks = [
                task.strip() for task in tasks_str.split('\n') 
                if task.startswith('- ') and len(task) > 2
            ]
            
            # 解析资源列表（过滤平台）
            daily_plan.resources = [
                resource.strip() for resource in resources_str.split('\n') 
                if resource.startswith('- ') and any(plat in resource.lower() for plat in ['b站', 'csdn', '知乎', '慕课网'])
            ]
            
            self.daily_plans.append(daily_plan)

# 初始化OpenAI客户端
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",  # DeepSeek API的基础URL
    timeout=6000.0  # 设置超时时间
)

def check_api_status():
    """检查API是否可用"""
    try:
        response = client.models.list()
        logger.info("API 状态: 连接成功")
        return True
    except Exception as e:
        logger.error(f"API 不可用: {str(e)}")
        return False

def network_diagnosis():
    """诊断网络连接问题"""
    print("\n🔍 网络诊断报告:")
    
    # 检查互联网连接
    try:
        socket.create_connection(("www.baidu.com", 80), timeout=5)
        print("✅ 互联网连接正常")
    except OSError:
        print("❌ 无法连接到互联网")
    
    # 检查 DeepSeek 域名解析
    for domain in ["api.deepseek.com", "api.deepseek.ai"]:
        try:
            socket.gethostbyname(domain)
            print(f"✅ 域名解析成功: {domain}")
        except socket.gaierror:
            print(f"❌ 无法解析域名: {domain} (检查DNS设置)")
    
    # 检查 API 端口
    for port in [443, 80]:
        try:
            with socket.create_connection(("api.deepseek.com", port), timeout=5):
                print(f"✅ 端口 {port} 可访问")
        except OSError:
            print(f"❌ 无法连接端口 {port} (可能被防火墙阻止)")

@dataclass
class User:
    id: int
    username: str
    email: str
    created_at: str
    learning_style: Optional[str] = None
    proficiency_level: Optional[str] = None

class DatabaseManager:
    def __init__(self, db_name: str = DB_NAME):
        self.db_name = db_name
        self._initialize_db()
    
    def _initialize_db(self) -> None:
        """初始化数据库表结构"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                # 用户表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        learning_style TEXT,
                        proficiency_level TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 学习计划表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS study_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        subject TEXT NOT NULL,
                        duration_days INTEGER NOT NULL CHECK(duration_days > 0),
                        target_level TEXT NOT NULL,
                        content TEXT NOT NULL,
                        status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'paused')),
                        progress REAL DEFAULT 0.0 CHECK(progress BETWEEN 0 AND 100),
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        last_updated TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                """)
                
                # 计划进度记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS plan_progress (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_id INTEGER NOT NULL,
                        day_number INTEGER NOT NULL CHECK(day_number > 0),
                        completed BOOLEAN DEFAULT 0,
                        notes TEXT,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (plan_id) REFERENCES study_plans (id) ON DELETE CASCADE,
                        UNIQUE(plan_id, day_number)
                    )
                """)
                
                # 用户反馈表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        plan_id INTEGER NOT NULL,
                        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                        comments TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                        FOREIGN KEY (plan_id) REFERENCES study_plans (id) ON DELETE CASCADE
                    )
                """)
                
                # 专注会话表（记录专注学习时间段）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS focus_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_id INTEGER NOT NULL,
                        day_number INTEGER NOT NULL,
                        task_name TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        duration_minutes INTEGER DEFAULT 0,
                        FOREIGN KEY (plan_id) REFERENCES study_plans (id) ON DELETE CASCADE
                    )
                """)
                
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"初始化数据库失败: {e}")
            raise
    
    def add_user(self, username: str, email: str, learning_style: str = None, proficiency_level: str = None) -> int:
        """添加用户到数据库"""
        if not username or not email:
            raise ValueError("用户名和邮箱不能为空")
        
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                # 检查邮箱是否已存在
                cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
                if existing := cursor.fetchone():
                    logger.info(f"邮箱 {email} 已注册，返回现有用户ID")
                    return existing[0]
                
                # 添加新用户
                cursor.execute(
                    "INSERT INTO users (username, email, learning_style, proficiency_level) VALUES (?, ?, ?, ?)",
                    (username, email, learning_style, proficiency_level)
                )
                conn.commit()
                return cursor.lastrowid
        
        except sqlite3.Error as e:
            logger.error(f"添加用户失败: {e}")
            raise
    
    def get_user(self, user_id: int) -> Optional[User]:
        """获取用户信息"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                row = cursor.fetchone()
                return User(*row) if row else None
        except sqlite3.Error as e:
            logger.error(f"获取用户信息失败: {e}")
            return None
    
    def add_study_plan(self, user_id: int, subject: str, duration_days: int, target_level: str, content: str) -> int:
        """添加学习计划"""
        if not subject or duration_days <= 0 or not target_level or not content:
            raise ValueError("无效的学习计划参数")
        
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO study_plans 
                    (user_id, subject, duration_days, target_level, content) 
                    VALUES (?, ?, ?, ?, ?)""",
                    (user_id, subject, duration_days, target_level, content)
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"添加学习计划失败: {e}")
            raise
    
    def get_study_plan(self, plan_id: int) -> Optional[StudyPlan]:
        """获取学习计划"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM study_plans WHERE id = ?", (plan_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                
                # 解析行数据到StudyPlan对象，并自动解析每日计划
                study_plan = StudyPlan(*row)
                study_plan.parse_daily_plans()
                return study_plan
        except sqlite3.Error as e:
            logger.error(f"获取学习计划失败: {e}")
            return None
    
    def update_plan_progress(self, plan_id: int, progress: float) -> bool:
        """更新计划进度"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE study_plans SET progress = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
                    (progress, plan_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"更新计划进度失败: {e}")
            return False
    
    def record_day_progress(self, plan_id: int, day_number: int, completed: bool, notes: str = "") -> bool:
        """记录每日进度"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO plan_progress 
                    (plan_id, day_number, completed, notes) 
                    VALUES (?, ?, ?, ?)""",
                    (plan_id, day_number, completed, notes)
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"记录每日进度失败: {e}")
            return False
    
    def add_feedback(self, user_id: int, plan_id: int, rating: int, comments: str = "") -> bool:
        """添加用户反馈"""
        if not 1 <= rating <= 5:
            raise ValueError("评分必须在1-5之间")
        
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO user_feedback 
                    (user_id, plan_id, rating, comments) 
                    VALUES (?, ?, ?, ?)""",
                    (user_id, plan_id, rating, comments)
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"添加用户反馈失败: {e}")
            return False
    
    def get_user_plans(self, user_id: int) -> List[StudyPlan]:
        """获取用户的所有学习计划"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM study_plans WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
                plans = []
                for row in cursor.fetchall():
                    plan = StudyPlan(*row)
                    plan.parse_daily_plans()
                    plans.append(plan)
                return plans
        except sqlite3.Error as e:
            logger.error(f"获取用户计划失败: {e}")
            return []

class StudyPlanAgent:
    def __init__(self):
        self.chat_history: List[Dict[str, str]] = []
    
    def _call_deepseek(self, prompt: str):
        """使用OpenAI库调用DeepSeek API"""
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是一个专业的学习规划助手"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"API调用失败: {str(e)}")
            raise

class GeneratorAgent(StudyPlanAgent):
    def generate_plan(self, subject: str, days: int, level: str, learning_style: str = None) -> str:
        """生成学习计划并解析响应"""
        prompt = self._build_prompt(subject, days, level, learning_style)
        response = self._call_deepseek(prompt)
        return self._parse_response(response, days)
    
    def _build_prompt(self, subject, days, level, learning_style=None):
        """构建标准化提示词"""
        style = learning_style or "通用"
        
        # 获取预设资源信息
        preset_resources_str = ""
        if subject.lower() in PRESET_RESOURCES:
            preset_resources_str = "\n## 预设资源清单\n"
            for resource in PRESET_RESOURCES[subject.lower()]:
                preset_resources_str += f"- [{resource['title']}]({resource['url']}) [{resource['platform']}]\n"
        
        return f"""
作为专业学习规划师，请为{subject}科目创建{days}天的详细学习计划，要求：
天数一定要严格按照我给的天数来
1. 【每日精确安排】必须包含每天的具体学习内容，格式为：
   - 第X天：
     - 核心知识点：[用一句话概括当天核心内容]
     - 学习任务：
       1. [具体任务1，包含估计时长]
       2. [具体任务2，包含估计时长]
       3. [具体任务3，包含估计时长]
     - 推荐资源：
       - [资源标题](URL) [平台名称]
       - [资源标题](URL) [平台名称]
     - 预计时长：[X小时]
     - 评估方法：[如何判断当天学习是否达标]

2. 【资源要求】
   - 视频和文章链接必须要是和学习内容相关的链接，不能有无效链接和不相关链接
   - 视频和文章链接必须要是和学习内容相关的链接，不能有无效链接和不相关链接
   - 视频和文章链接必须要是和学习内容相关的链接，不能有无效链接和不相关链接
   - 不要空链接，请检查链接
   - 不要空链接，请检查链接
   - 不要空链接，请检查链接
   -好好检查你给我的资源
   - 视频资源必须来自B站，建议寻找b站的系列视频。如果找到了系列视频，建议先总起说一下你找到了什么系列视频，然后在不同天的学习视频中引用这个系列的子视频，子视频要和学习任务对应。
   - 文章类资源建议来自CSDN或知乎
   - 课程类资源可来自慕课网
   - 所有资源必须标注平台名称
   - 优先使用以下预设资源（如果适用）：
{preset_resources_str}
   - 不要给我内容不符合要求的垃圾链接！！！！！

3. 【阶段划分】将{days}天分为3个阶段：
   - 基础阶段（1-{max(3, days//3)}天）：掌握基础概念和工具使用
   - 进阶阶段（{max(4, days//3+1)}-{2*days//3}天）：深入原理与实战训练
   - 实战阶段（{2*days//3+1}-{days}天）：完整项目实战与总结

4. 【学习风格适配】针对{style}学习风格，在资源推荐和任务设计上侧重{self._get_style_adaptation(style)}

5. 【输出格式】严格使用以下Markdown结构：
   ## 一、学习目标
   {self._get_level_target(level)}
   ## 二、阶段划分
   ### 基础阶段（第1-{max(3, days//3)}天）
   [简要说明此阶段目标]
   ### 进阶阶段（第{max(4, days//3+1)}-{2*days//3}天）
   [简要说明此阶段目标]
   ### 实战阶段（第{2*days//3+1}-{days}天）
   [简要说明此阶段目标]
   ## 三、每日详细计划
   [按顺序列出每天内容，严格使用上述格式]
   ## 四、推荐资源清单
   [按平台分类整理所有推荐资源]
""".strip()

    def _get_level_target(self, level: str) -> str:
        """根据目标水平生成具体学习目标"""
        level_map = {
            "入门": f"掌握{level}所需的基础概念、工具和方法，能够完成简单的{level}任务",
            "精通": f"深入理解{level}的核心原理和高级技术，能够独立设计和实现复杂的{level}项目",
            "专家": f"掌握{level}领域的前沿知识和最佳实践，能够指导团队解决最具挑战性的{level}问题"
        }
        return f"目标：达到{level}水平，{level_map[level]}"

    def _get_style_adaptation(self, style: str) -> str:
        """根据学习风格调整教学方法"""
        style_map = {
            "视觉型": "图表、流程图和视频演示",
            "听觉型": "音频讲解和播客资源",
            "动手实践型": "项目实战和代码练习",
            "通用": "图文结合、案例分析和实操练习"
        }
        return style_map.get(style, "通用教学方法")

    def _parse_response(self, response: str, total_days: int) -> str:
        """解析并验证API响应，并用本地资源替换不合格资源"""

        # ✅ 1. 检查阶段划分是否完整
        phases = ["基础阶段", "进阶阶段", "实战阶段"]
        if not all(phase in response for phase in phases):
            raise ValueError(f"生成的计划缺少以下阶段: {', '.join([p for p in phases if p not in response])}")

        # ✅ 2. 检查是否有每日计划
        daily_pattern = re.compile(r'### 第(\d+)天')
        daily_matches = daily_pattern.findall(response)
        if not daily_matches:
            raise ValueError("生成的计划中未找到每日计划内容")

        actual_days = sorted(map(int, daily_matches))
        expected_days = list(range(1, total_days + 1))
        if actual_days != expected_days:
            missing_days = [d for d in expected_days if d not in actual_days]
            raise ValueError(f"计划天数不完整，缺少第{', '.join(map(str, missing_days))}天")

        # ✅ 3. 查找所有资源链接，并判断是否合规
        resource_pattern = re.compile(r'- \[(.*?)\]\((.*?)\) \[(.*?)\]')
        invalid_lines = []
        for match in resource_pattern.finditer(response):
            title, url, platform = match.groups()
            platform = platform.lower()
            if not url.strip() or platform not in ['b站', 'csdn', '知乎', '慕课网']:
                invalid_lines.append(match.group())

        # ✅ 4. 如果发现不合规链接，尝试从本地预设资源中找替代
        if invalid_lines:
            for invalid in invalid_lines:
                # 猜测当前主题关键词（可以通过调用者传进来更准确）
                subject_keywords = list(PRESET_RESOURCES.keys())
                for keyword in subject_keywords:
                    for replacement in PRESET_RESOURCES[keyword]:
                        # 构造替代格式
                        new_line = f"- [{replacement['title']}]({replacement['url']}) [{replacement['platform']}]"
                        if keyword.lower() in response.lower():
                            response = response.replace(invalid, new_line, 1)
                            break
                    else:
                        continue
                    break

        return response

        
class ReviewerAgent(StudyPlanAgent):
    """学习计划审核器"""
    def review_plan(self, plan: str) -> Tuple[bool, str]:
        if not plan:
            raise ValueError("计划内容不能为空")
        
        prompt = (
            "请严格审核以下学习计划，首先最为必要的是检查每一个链接，到底是不是有效并且和学习内容相关的链接？另外，检查是否存在这些问题，最重要的是关注链接，不要给我空网页！也不要给我牛头不对马嘴的网页：\n"
            "1. 知识点覆盖是否全面\n"
            "2. 时间分配是否合理\n"
            "3. 是否包含非B站/CSDN/知乎/慕课网的外部资源\n"
            "4. 是否符合学习者的目标水平\n"
            "5. 每日目标是否明确可衡量\n\n"
            "6. 给出的网站资源内容和要求是否一致，不要是不相关内容"
            "7. 给出的网站资源是否尽量系统，尽量来自同一个平台同一个系列"
            '- 视频和文章链接必须要是和学习内容相关的链接，不能有无效链接和不相关链接'
            '- 视频和文章链接必须要是和学习内容相关的链接，不能有无效链接和不相关链接'
            '- 视频和文章链接必须要是和学习内容相关的链接，不能有无效链接和不相关链接'
            ' - 不要空链接，请检查链接'
            '- 不要空链接，请检查链接'
            '- 不要空链接，请检查链接'
            '-好好检查你给我的资源'
            f"计划内容：\n{plan}\n\n"
            "请按以下格式回复：\n"
            "【是否合理】是/否\n"
            "【修改建议】(如果不合理，请具体说明)"
        )
        response = self._call_deepseek(prompt)
        return self._parse_response(response)
    
    def _parse_response(self, response: str) -> Tuple[bool, str]:
        """解析审核结果"""
        lines = response.split("\n")
        is_valid = any("【是否合理】是" in line for line in lines)
        
        suggestion = ""
        for i, line in enumerate(lines):
            if "【修改建议】" in line:
                suggestion = "\n".join(lines[i+1:]).strip()
                break
        
        return is_valid, suggestion

class VideoAuditAgent(StudyPlanAgent):
    """视频资源审核 Agent3"""
    def audit_video_resources(self, plan: str) -> Tuple[bool, str]:
        if not plan:
            raise ValueError("计划内容不能为空")

        prompt = (
            "你是一个专业的学习资源审核员，负责检查学习计划中每天提供的视频和文章资源的质量。\n"
            "你必须逐条检查每一个资源，判断是否：\n"
            "1. 链接是否有效（不要是空链接、无效链接、无法访问、404 页面、重定向无效、广告页等）\n"
            "2. 是否和该天的学习任务内容紧密相关（标题、内容必须匹配任务目标）\n"
            "3. 是否来自以下平台：B站、CSDN、知乎、慕课网，其他平台一律不接受\n"
            "4. 视频类资源是否是系列课程中的一部分（优先选系列视频）\n\n"
            "✅ 如果某个资源合格，请在结果中标明 “【合格】” 并说明原因\n"
            "❌ 如果某个资源不合格，请写明不合格原因，并推荐 1 个新的合格资源（真实存在、标题相关、平台符合）\n\n"
            "请按如下格式输出（对每一条资源都必须列出）：\n"
            "- 第X天 第Y条资源：\n"
            "  原资源：[标题](链接) [平台]\n"
            "  检查结果：【合格】/【不合格】原因：xxx\n"
            "  推荐替代资源（如不合格）：[新标题](新链接) [平台]\n\n"
            f"以下是完整学习计划内容：\n{plan}\n"
        )

        response = self._call_deepseek(prompt)
        return self._parse_response(response)
    
    def _parse_response(self, response: str) -> Tuple[bool, str]:
        lines = response.split("\n")
        is_valid = any("【视频资源审核结果】合格" in line for line in lines)
        suggestion = ""
        for i, line in enumerate(lines):
            if "【视频资源建议】" in line:
                suggestion = "\n".join(lines[i+1:]).strip()
                break
        return is_valid, suggestion


class ProgressTracker:
    """学习进度跟踪器"""
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def update_progress(self, plan_id: int, day_number: int, completed: bool, notes: str = "") -> bool:
        """更新每日进度"""
        if not self.db.record_day_progress(plan_id, day_number, completed, notes):
            return False
        
        # 计算整体进度
        plan = self.db.get_study_plan(plan_id)
        if not plan:
            return False
        
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM plan_progress WHERE plan_id = ? AND completed = 1",
                    (plan_id,)
                )
                completed_days = cursor.fetchone()[0]
                progress = min(100.0, (completed_days / plan.duration_days) * 100)
                return self.db.update_plan_progress(plan_id, progress)
        except sqlite3.Error as e:
            logger.error(f"计算进度失败: {e}")
            return False
    
    def get_plan_progress(self, plan_id: int) -> Dict[str, Any]:
        """获取计划进度详情"""
        plan = self.db.get_study_plan(plan_id)
        if not plan:
            return {}
        
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT day_number, completed, notes 
                    FROM plan_progress 
                    WHERE plan_id = ? 
                    ORDER BY day_number""",
                    (plan_id,)
                )
                daily_progress = cursor.fetchall()
                
                cursor.execute(
                    "SELECT COUNT(*) FROM plan_progress WHERE plan_id = ? AND completed = 1",
                    (plan_id,)
                )
                completed_days = cursor.fetchone()[0]
                
                return {
                    "plan_id": plan_id,
                    "subject": plan.subject,
                    "total_days": plan.duration_days,
                    "completed_days": completed_days,
                    "progress_percentage": plan.progress,
                    "daily_progress": [
                        {"day": day, "completed": bool(completed), "notes": notes}
                        for day, completed, notes in daily_progress
                    ]
                }
        except sqlite3.Error as e:
            logger.error(f"获取进度详情失败: {e}")
            return {}

class FocusManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.active_session = None  # 存储当前活跃的专注会话
    
    def start_focus(self, plan_id: int, day_number: int, task_name: str):
        """开始专注任务"""
        if self.active_session:
            raise ValueError("已有正在进行的专注会话")
        
        start_time = datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO focus_sessions (plan_id, day_number, task_name, start_time) VALUES (?, ?, ?, ?)",
                    (plan_id, day_number, task_name, start_time)
                )
                self.active_session = {
                    "id": cursor.lastrowid,
                    "plan_id": plan_id,
                    "day_number": day_number,
                    "task_name": task_name,
                    "start_time": start_time
                }
                conn.commit()
                print(f"🚀 专注模式开始：{task_name}")
                return self.active_session
        except sqlite3.Error as e:
            logger.error(f"开始专注会话失败: {e}")
            return None
    
    def end_focus(self):
        """结束专注任务"""
        if not self.active_session:
            raise ValueError("没有正在进行的专注会话")
        
        end_time = datetime.now().isoformat()
        start_time = datetime.fromisoformat(self.active_session["start_time"])
        duration = (datetime.now() - start_time).total_seconds() // 60  # 转换为分钟
        
        try:
            with sqlite3.connect(self.db.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE focus_sessions SET end_time = ?, duration_minutes = ? WHERE id = ?",
                    (end_time, duration, self.active_session["id"])
                )
                conn.commit()
                
                # 自动更新计划进度
                plan_id = self.active_session["plan_id"]
                day_number = self.active_session["day_number"]
                task_name = self.active_session["task_name"]
                
                # 检查当天是否已完成
                cursor.execute(
                    "SELECT completed FROM plan_progress WHERE plan_id = ? AND day_number = ?",
                    (plan_id, day_number)
                )
                result = cursor.fetchone()
                
                # 如果当天未完成，标记为完成
                if result is None or not result[0]:
                    self.db.record_day_progress(plan_id, day_number, True, f"专注任务: {task_name} ({duration}分钟)")
                    self.update_overall_progress(plan_id)
                
                print(f"📊 专注结束：{task_name}，累计学习 {duration} 分钟")
                self.active_session = None  # 清空当前会话
                return {"duration": duration, **self.active_session}
        except sqlite3.Error as e:
            logger.error(f"结束专注会话失败: {e}")
            return None
    
    def update_overall_progress(self, plan_id: int):
        """更新整体进度"""
        plan = self.db.get_study_plan(plan_id)
        if not plan:
            return False
        
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM plan_progress WHERE plan_id = ? AND completed = 1",
                    (plan_id,)
                )
                completed_days = cursor.fetchone()[0]
                progress = min(100.0, (completed_days / plan.duration_days) * 100)
                return self.db.update_plan_progress(plan_id, progress)
        except sqlite3.Error as e:
            logger.error(f"计算进度失败: {e}")
            return False
    
    def get_weekly_focus_time(self, plan_id: int, week_num: int = None) -> int:
        """获取指定计划的周累计学习时间（分钟）"""
        today = datetime.now()
        if not week_num:
            week_num = today.isocalendar()[1]  # 获取当前周数
        
        start_week = today - timedelta(days=today.weekday())
        end_week = start_week + timedelta(days=6)
        
        try:
            with sqlite3.connect(self.db.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT SUM(duration_minutes) FROM focus_sessions 
                    WHERE plan_id = ? 
                    AND start_time BETWEEN ? AND ?
                """, (plan_id, start_week.isoformat(), end_week.isoformat()))
                total_minutes = cursor.fetchone()[0] or 0
                return total_minutes
        except sqlite3.Error as e:
            logger.error(f"查询周学习时间失败: {e}")
            return 0

class WeeklyReportGenerator:
    def __init__(self, db_manager: DatabaseManager, focus_manager: FocusManager):
        self.db = db_manager
        self.focus = focus_manager
    
    def generate_weekly_report(self, user_id: int, plan_id: int) -> str:
        """生成周学习报告"""
        plan = self.db.get_study_plan(plan_id)
        if not plan:
            return "❌ 计划不存在"
        
        # 获取本周专注时间
        weekly_time = self.focus.get_weekly_focus_time(plan_id)
        
        # 获取本周完成的任务
        today = datetime.now()
        start_week = today - timedelta(days=today.weekday())
        end_week = start_week + timedelta(days=6)
        
        try:
            with sqlite3.connect(self.db.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT day_number, completed, notes FROM plan_progress 
                    WHERE plan_id = ? 
                    AND updated_at BETWEEN ? AND ?
                """, (plan_id, start_week.isoformat(), end_week.isoformat()))
                weekly_tasks = cursor.fetchall()
                
                # 获取本周专注任务
                cursor.execute("""
                    SELECT task_name, duration_minutes, start_time FROM focus_sessions 
                    WHERE plan_id = ? 
                    AND start_time BETWEEN ? AND ?
                """, (plan_id, start_week.isoformat(), end_week.isoformat()))
                focus_tasks = cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"查询周任务失败: {e}")
            weekly_tasks = []
            focus_tasks = []
        
        # 构建报告内容
        report = f"""
📅 周报（{start_week.strftime('%Y-%m-%d')} - {end_week.strftime('%Y-%m-%d')}）
============================
📌 学习计划：{plan.subject}
⏳ 累计学习时间：{weekly_time} 分钟
✅ 完成任务：
"""
        for day, completed, notes in weekly_tasks:
            status = "✅" if completed else "❌"
            report += f"- 第{day}天：{status} {notes}\n"
        
        report += "\n🔍 专注任务详情：\n"
        for task, duration, start_time in focus_tasks:
            task_date = datetime.fromisoformat(start_time).strftime('%Y-%m-%d')
            report += f"- {task_date}：{task} ({duration}分钟)\n"
        
        # 进度条
        progress = plan.progress
        report += f"\n📊 总体进度：{create_progress_bar(progress)}"
        
        return report.strip()

def create_progress_bar(progress: float, length: int = 30) -> str:
    """生成进度条字符串"""
    filled = int(progress / 100 * length)
    empty = length - filled
    return f"[{'█' * filled}{'-' * empty}] {progress:.1f}%"

def save_to_markdown(content: str, filename: str = "study_plan.md") -> None:
    """保存计划到Markdown文件"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"学习计划已保存为 {filename}")
    except IOError as e:
        logger.error(f"保存文件失败: {e}")
        raise

def display_plan_summary(plan: StudyPlan) -> None:
    """显示计划摘要"""
    if not plan:
        logger.warning("无效的学习计划")
        return
    
    print("\n📋 计划摘要:")
    print(f"主题: {plan.subject}")
    print(f"天数: {plan.duration_days} 天")
    print(f"目标水平: {plan.target_level}")
    print(f"创建时间: {plan.created_at}")
   # print(f"进度: {float(plan.progress):.1f}%")

def get_user_input() -> Tuple[str, str, Optional[str], str, int, str]:
    """获取用户输入"""
    print("\n🎓 DeepSeek AI 学习计划生成系统 (增强版)")
    print("=" * 50)
    
    while True:
        username = input("请输入您的用户名: ").strip()
        if username:
            break
        print("用户名不能为空")
    
    while True:
        email = input("请输入您的邮箱: ").strip()
        if "@" in email and "." in email.split("@")[-1]:
            break
        print("请输入有效的邮箱地址")
    
    learning_style = input("请输入您的学习风格(可选，如视觉/听觉/动手实践): ").strip() or None
    
    while True:
        subject = input("\n请输入你要学习的科目: ").strip()
        if subject:
            break
        print("科目不能为空")
    
    while True:
        try:
            days = int(input("请输入你希望学习的天数(如 10): ").strip())
            if days > 0:
                break
            print("天数必须大于0")
        except ValueError:
            print("请输入有效的数字")
    
    while True:
        level = input("请输入你希望达到的水平(入门/精通/专家): ").strip()
        if level in ["入门", "精通", "专家"]:
            break
        print("请输入有效的水平选项(入门/精通/专家)")
    
    return username, email, learning_style, subject, days, level

def main():
    try:
        # 检查API状态
        if not check_api_status():
            print("❌ 无法连接到DeepSeek API，请检查网络连接或API密钥")
            network_diagnosis()
            return
        
        # 初始化数据库
        db = DatabaseManager()
        
        # 获取用户输入
        username, email, learning_style, subject, days, level = get_user_input()
        
        # 添加用户到数据库
        try:
            user_id = db.add_user(username, email, learning_style, level)
            logger.info(f"用户 {username} 注册成功，ID: {user_id}")
        except Exception as e:
            logger.error(f"用户注册失败: {e}")
            return
        
        # 初始化Agent
        generator = GeneratorAgent()
        reviewer = ReviewerAgent()
        video_auditor = VideoAuditAgent()
        progress_tracker = ProgressTracker(db)
        focus_manager = FocusManager(db)
        report_generator = WeeklyReportGenerator(db, focus_manager)
        
        # 生成初始计划
        print("\n⏳ Agent1 正在生成学习计划...")
        try:
            plan_content = generator.generate_plan(subject, days, level, learning_style)
        except Exception as e:
            logger.error(f"生成学习计划失败: {e}")
            return
        
        # 保存计划到数据库
        try:
            plan_id = db.add_study_plan(user_id, subject, days, level, plan_content)
            plan = db.get_study_plan(plan_id)
            logger.info(f"学习计划创建成功，ID: {plan_id}")
        except Exception as e:
            logger.error(f"保存学习计划失败: {e}")
            return
        
        # 显示计划
        print("\n✅ 初始学习计划：")
        display_plan_summary(plan)
        print("\n" + plan_content ) 
        
        # 审核计划
        print("\n🔍 Agent2 正在审核计划合理性...")
        try:
            is_valid, suggestion = reviewer.review_plan(plan_content)
            print("\n" + suggestion)    
        except Exception as e:
            logger.error(f"审核计划失败: {e}")
            is_valid, suggestion = False, "审核过程中出现错误"
        
        # 处理审核结果
        if not is_valid:
            print("\n⚠️ Agent2 审核未通过，正在重新生成...")
            try:
                plan_content = generator.generate_plan(subject, days, level, learning_style)
                print('\n' + plan_content)
            except Exception as e:
                logger.error(f"Agent1 根据 Agent2 建议优化失败: {e}")
                return

        # Agent3 视频审核
        print("\n🎞️ Agent3 正在审核视频资源...")
        try:
            video_valid, video_suggestion = video_auditor.audit_video_resources(plan_content)
            print("\n" + video_suggestion)
        except Exception as e:
            logger.error(f"视频审核失败: {e}")
            video_valid, video_suggestion = False, "视频审核过程中出现错误"

        if not video_valid:
            print("\n⚠️ 视频资源存在问题：")
            print(video_suggestion)
            print("\n🛠️ Agent1 正在根据视频审核建议优化学习计划...")
            try:
                plan_content = generator.generate_plan(subject, days, level, learning_style)
                print('\n'+plan_content)
            except Exception as e:
                logger.error(f"根据 Agent3 视频审核建议优化失败: {e}")
                return

        # 最终保存并展示
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE study_plans SET content = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
                    (plan_content, plan_id)
                )
                conn.commit()
            plan = db.get_study_plan(plan_id)
            print("\n✅ 最终学习计划：")
            display_plan_summary(plan)
            print("\n" + plan_content)
            save_to_markdown(plan_content, f"final_study_plan_{plan_id}.md")
        except Exception as e:
            logger.error(f"保存最终计划失败: {e}")

        
        # 主交互循环
        while True:
            print("\n" + "=" * 50)
            print("\n🎓 学习计划管理系统")
            print("1. 开始专注任务")
            print("2. 结束专注任务")
            print("3. 查看进度")
            print("4. 查看周报")
            print("5. 手动更新进度")
            print("6. 查看今日任务")
            print("7. 退出")
            
            choice = input("\n请选择操作: ").strip()
            
            if choice == "1":
                # 显示当前计划天数
                print(f"\n📅 当前计划总天数: {plan.duration_days}")
                while True:
                    try:
                        day_number = int(input("请输入当前学习的天数: ").strip())
                        if 1 <= day_number <= plan.duration_days:
                            break
                        print(f"天数必须在 1-{plan.duration_days} 之间")
                    except ValueError:
                        print("请输入有效的数字")
                
                task_name = input("请输入任务名称: ").strip()
                if not task_name:
                    print("任务名称不能为空")
                    continue
                
                focus_manager.start_focus(plan_id, day_number, task_name)
            
            elif choice == "2":
                try:
                    focus_manager.end_focus()
                except ValueError as e:
                    print(e)
            
            elif choice == "3":
                progress = progress_tracker.get_plan_progress(plan_id)
                if not progress:
                    print("❌ 获取进度失败")
                    continue
                
                print(f"\n📊 当前进度: {create_progress_bar(progress['progress_percentage'])}")
                print(f"完成度：{progress['progress_percentage']:.1f}%")
                print(f"已完成天数: {progress['completed_days']}/{progress['total_days']}")
                
                # 显示最近3天进度
                print("\n最近进度:")
                for day in sorted(progress['daily_progress'], key=lambda x: x['day'], reverse=True)[:3]:
                    status = "✅" if day['completed'] else "❌"
                    print(f"- 第{day['day']}天: {status} {day['notes']}")
            
            elif choice == "4":
                report = report_generator.generate_weekly_report(user_id, plan_id)
                print("\n" + report)
            
            elif choice == "5":
                # 手动更新进度
                print(f"\n📅 当前计划总天数: {plan.duration_days}")
                while True:
                    try:
                        day_number = int(input("请输入要更新的天数: ").strip())
                        if 1 <= day_number <= plan.duration_days:
                            break
                        print(f"天数必须在 1-{plan.duration_days} 之间")
                    except ValueError:
                        print("请输入有效的数字")
                
                while True:
                    completed_input = input("是否完成? (y/n): ").strip().lower()
                    if completed_input in ('y', 'n'):
                        completed = completed_input == 'y'
                        break
                    print("请输入 y 或 n")
                
                notes = input("请输入备注(可选): ").strip()
                
                if progress_tracker.update_progress(plan_id, day_number, completed, notes):
                    print("✅ 进度更新成功")
                else:
                    print("❌ 进度更新失败")
            
            elif choice == "6":
                # 查看今日任务
                today = datetime.now().day % plan.duration_days
                if today == 0:
                    today = plan.duration_days
                
                print(f"\n📅 第{today}天学习计划：")
                if plan and plan.daily_plans:
                    today_plan = next((dp for dp in plan.daily_plans if dp.day_number == today), None)
                    if today_plan:
                        print("\n📝 任务清单：")
                        for i, task in enumerate(today_plan.tasks, 1):
                            print(f"{i}. {task}")
                        
                        print("\n📚 推荐资源：")
                        for resource in today_plan.resources:
                            print(f"- {resource}")
                        
                        print(f"\n🔍 评估方法：{today_plan.assessment}")
                    else:
                        print("今日计划未找到，请检查计划内容")
                else:
                    print("计划或每日计划数据不可用")
            
            elif choice == "7":
                break
            
            else:
                print("❌ 无效选择，请重新输入")
        
        # 收集反馈
        print("\n💬 请提供反馈帮助我们改进:")
        while True:
            try:
                rating = int(input("请评分(1-5星): ").strip())
                if 1 <= rating <= 5:
                    break
                print("评分必须在1-5之间")
            except ValueError:
                print("请输入有效的数字")
        
        comments = input("请输入您的意见或建议: ").strip()
        
        try:
            if not db.add_feedback(user_id, plan_id, rating, comments):
                logger.warning("添加反馈失败")
            else:
                logger.info("感谢您的反馈！")
        except Exception as e:
            logger.error(f"保存反馈失败: {e}")
        
        print("\n👋 程序结束。感谢使用学习计划生成系统！")
    
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        print("\n⚠️ 程序运行中发生错误，请查看日志获取详细信息")

if __name__ == "__main__":
    main()

