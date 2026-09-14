#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 出题质量检测脚本 (quality_check.py)
======================================

用途
----
在写任何前端代码之前，先验证这个项目最危险的假设：
**「输入一段文字 → AI 产出的题目质量是否足够好」**。

本脚本会：
  1. 取一段知识文本（内置 20 个跨领域样例，或你自己提供）
  2. 调用大模型生成"知识点大纲 + 题目 + 讲解"的结构化结果
  3. 对生成结果做 12 类自动质量检查
  4. 输出一份人工可读的 Markdown 报告 + 原始 JSON 存档

两种运行模式
------------
  * 离线模式  --mock      使用内置的模拟数据，不需要 API Key。
                          用于验证脚本本身、演示检查项。
  * 在线模式  （默认）    真正调用大模型，需要设置环境变量。

环境变量
--------
  LLM_API_KEY | DEEPSEEK_API_KEY   API Key（在线模式必填）
  LLM_BASE_URL                     默认 https://api.deepseek.com
  LLM_MODEL                        默认 deepseek-flash

用法示例
--------
  # 离线自检（推荐先跑这个，确认脚本没问题）
  python quality_check.py --mock

  # 在线跑全部 20 个样例
  python quality_check.py

  # 只跑前 3 个样例
  python quality_check.py --limit 3

  # 用自己的文本
  python quality_check.py --text "光合作用是植物利用光能……"
  python quality_check.py --file my_note.txt

  # 只打印将要发送给模型的提示词，不调用 API
  python quality_check.py --dry-run

依赖
----
仅使用 Python 标准库，无需 pip install。需要 Python 3.10+。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

VERSION = "0.1.0"

# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

DEFAULT_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "deepseek-flash")
DEFAULT_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "180"))
DEFAULT_OUTDIR = str(Path(__file__).resolve().parent / "reports")

# 质量阈值（集中在这里，方便后续按实测结果调整）
MIN_QUESTIONS = 8
MAX_QUESTIONS = 12
MIN_EXPLANATION_CHARS = 40
MIN_STEM_CHARS = 6                # 判断题与"XX是指？"这类短题干是正常的
MAX_STEM_CHARS = 150
DUPLICATE_STEM_RATIO = 0.90
DUPLICATE_OPTION_OVERLAP = 0.75   # 判"重复题"时，选项也要有这么多重合
ANSWER_SKEW_RATIO = 0.60          # 单一选项占比超过此值 -> 警告

PENALTY = {"error": 8, "warn": 3}

# 模型返回的 JSON 解析失败时，自动重试的次数
PARSE_RETRIES = 2

# 出现这些错误说明是账号或密钥层面的问题，重试和继续执行都没有意义
FATAL_ERROR_MARKERS = ("HTTP 401", "HTTP 402", "HTTP 403")


def is_fatal_error(message: str) -> bool:
    """判断是否是"继续跑下去也没用"的错误（密钥无效 / 余额不足 / 无权限）。"""
    return any(marker in message for marker in FATAL_ERROR_MARKERS)

# 低质量选项（教研上公认的"送分/无效"选项）
LOW_QUALITY_OPTION_PATTERNS = [
    r"以上(都|均|全)(对|正确|是|错|不正确|不对)",
    r"以上选项(都|均)",
    r"^(都|均)不正确$",
    r"^(都|均)不对$",
    r"全部(都)?(正确|不正确|对|错)$",
]

JUDGE_OPTION_TEXTS = {"正确", "错误", "对", "错", "是", "否", "true", "false"}
VALID_TYPES = {"single", "multiple", "judge"}

# 选项字母后面不能紧跟其它字母或数字。
# 否则「正确选项是DNA的一条链」里的 D 会被误当成选项 D（中英混排陷阱）。
_OPT_LETTER = r"([A-D](?![A-Za-z0-9_])(?:\s*[、,，和及与]\s*[A-D](?![A-Za-z0-9_]))*)"

# 讲解中"断言答案是 X"的表述，例如"正确选项是 C""正确答案应为 A、B、C"
ANSWER_ASSERT_RE = re.compile(
    r"(?:正确选项|正确答案|参考答案|标准答案|本题答案|答案)\s*"
    r"(?:是|为|应为|应该是|：|:)?\s*"
    + _OPT_LETTER
)
# "故选 X""应选 X"这类表述，需要结合上下文判断是肯定还是否定
CHOICE_RE = re.compile(r"选\s*([A-D](?![A-Za-z0-9_]))")
# 否定/假设语境：出现在选项字母之前或之后，说明这是在解释"错误选项"
NEG_HEAD_RE = re.compile(r"(?:不|未|别|勿|排除|排除掉)$")
NEG_TAIL_RE = re.compile(
    r"^\s*(?:项)?\s*(?:错误|错的|错|不对|不正确|有误|不符合|不成立|相反|不合适|不恰当|无关)"
)
HYPOTHESIS_HEAD_RE = re.compile(r"(?:若|如果|假若|假如|倘若)$")


def extract_asserted_answers(explanation: str) -> list[str]:
    """抽取讲解中**断言为正确答案**的选项字母。

    刻意忽略否定语境。因为"故不选D""若选B则与原文相反"是解释错误选项的
    标准教学写法，而非答案不一致。早期版本没有区分语境，导致大量误报。
    """
    asserted: list[str] = []

    for m in ANSWER_ASSERT_RE.finditer(explanation):
        asserted += re.findall(r"[A-D]", m.group(1))

    for m in CHOICE_RE.finditer(explanation):
        head = explanation[max(0, m.start() - 5):m.start()]
        tail = explanation[m.end():m.end() + 12]
        if NEG_HEAD_RE.search(head):        # 故不选D / 排除B
            continue
        if HYPOTHESIS_HEAD_RE.search(head):  # 若选B则……
            continue
        if NEG_TAIL_RE.match(tail):          # 故选D错误 / 选C不对
            continue
        asserted.append(m.group(1))

    return asserted


# --------------------------------------------------------------------------- #
# 内置样例：20 个跨领域知识文本
# --------------------------------------------------------------------------- #

SAMPLES: list[dict[str, str]] = [
    {
        "id": "s01",
        "domain": "金融",
        "title": "货币政策三大工具",
        "text": (
            "中央银行调节货币供应量的三大传统工具是存款准备金率、再贴现率和公开市场操作。"
            "存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例，提高准备金率会"
            "减少商业银行可用于放贷的资金，从而收紧货币供应。再贴现率是商业银行向央行借款的利率，"
            "提高再贴现率会提高商业银行的融资成本，抑制其借款意愿。公开市场操作是央行在金融市场上"
            "买卖有价证券的行为，买入证券会向市场投放基础货币，属于扩张性政策；卖出证券则回笼资金。"
            "三大工具中，公开市场操作最为灵活、使用最频繁；存款准备金率的作用最猛烈，通常被视为"
            "一剂猛药，不宜频繁使用。"
        ),
    },
    {
        "id": "s02",
        "domain": "物理",
        "title": "光的折射与全反射",
        "text": (
            "光从一种介质斜射入另一种介质时，传播方向会发生偏折，这种现象叫光的折射。折射定律指出："
            "入射角的正弦与折射角的正弦之比等于两种介质折射率之比，且入射光线、折射光线和法线在同一"
            "平面内，入射光线与折射光线分居法线两侧。当光从光密介质射向光疏介质，且入射角大于临界角时，"
            "折射光消失，光线全部被反射回原介质，这就是全反射。临界角的正弦等于光疏介质折射率与光密"
            "介质折射率之比。光纤通信正是利用全反射原理，让光信号在纤芯中不断反射向前传播，从而实现"
            "低损耗、大容量的信息传输。"
        ),
    },
    {
        "id": "s03",
        "domain": "生物",
        "title": "细胞呼吸的两种方式",
        "text": (
            "细胞呼吸分为有氧呼吸和无氧呼吸。有氧呼吸是细胞在氧的参与下，将葡萄糖等有机物彻底氧化"
            "分解，释放大量能量并生成二氧化碳和水的过程，主要场所是线粒体。它分为三个阶段：糖酵解在"
            "细胞质基质中进行，产生少量ATP；柠檬酸循环在线粒体基质中进行；氧化磷酸化在线粒体内膜上"
            "进行，产生绝大部分ATP。无氧呼吸则在缺氧条件下进行，有机物分解不彻底，产物是乳酸或酒精"
            "和二氧化碳，释放能量远少于有氧呼吸。人体剧烈运动时肌肉细胞会进行无氧呼吸产生乳酸，导致"
            "肌肉酸胀；酵母菌在无氧条件下则进行酒精发酵。"
        ),
    },
    {
        "id": "s04",
        "domain": "历史",
        "title": "文艺复兴的核心特征",
        "text": (
            "文艺复兴是14世纪到17世纪在欧洲兴起的一场思想文化运动，发源于意大利，后扩展到西欧各国。"
            "它的核心是人文主义，主张以人为中心而不是以神为中心，肯定人的价值和尊严，反对教会对人的"
            "束缚。文艺复兴的思想基础是复兴古希腊罗马的古典文化，但并非简单复古，而是借古典文化来"
            "表达新的资产阶级思想。它在文学、艺术、科学等领域都有突出成就：但丁的《神曲》、达芬奇的"
            "《蒙娜丽莎》、莎士比亚的戏剧都是代表。印刷术的传播极大加速了思想的扩散。文艺复兴推动了"
            "宗教改革和近代自然科学的兴起，被视为欧洲近代史的开端。"
        ),
    },
    {
        "id": "s05",
        "domain": "计算机",
        "title": "二分查找的前提与复杂度",
        "text": (
            "二分查找是一种在有序数组中查找目标元素的高效算法。它的基本思想是：每次取数组中间位置的"
            "元素与目标值比较，若相等则查找成功；若中间元素小于目标值，则在右半部分继续查找；否则在"
            "左半部分继续查找，直到找到目标或区间为空。二分查找的前提是数据必须有序，且支持随机访问，"
            "因此适用于数组而不适用于链表。它的时间复杂度是 O(log n)，空间复杂度在迭代实现下为 O(1)，"
            "递归实现下为 O(log n)。实现时最容易出错的地方是中间位置的计算和边界条件的处理，例如写成"
            " mid = (low + high) / 2 在 low 和 high 都很大时可能整数溢出，安全的写法是 mid = low + (high - low) / 2。"
        ),
    },
    {
        "id": "s06",
        "domain": "法律",
        "title": "行政复议与行政诉讼的区别",
        "text": (
            "行政复议和行政诉讼都是公民、法人或其他组织认为行政机关的具体行政行为侵犯其合法权益时"
            "寻求救济的途径，但两者有本质区别。受理机关不同：行政复议由上一级行政机关或同级人民政府"
            "受理，属于行政系统内部的层级监督；行政诉讼由人民法院受理，属于司法监督。审查范围不同："
            "行政复议既审查合法性也审查适当性；行政诉讼原则上只审查合法性，一般不审查合理性。程序"
            "不同：行政复议程序简便、不收费、审理期限短；行政诉讼程序严格、收取诉讼费、实行两审终审。"
            "两者的衔接上，多数情形下当事人可以自由选择先复议或直接起诉，但对某些特定行为法律规定"
            "复议前置。"
        ),
    },
    {
        "id": "s07",
        "domain": "考公-行测",
        "title": "资料分析中的增长率与增长量",
        "text": (
            "在资料分析中，增长量指现期量减去基期量的差值，增长率指增长量除以基期量得到的比值，通常"
            "用百分数表示。已知现期量和增长率求基期量的公式是：基期量 = 现期量 / (1 + 增长率)。已知"
            "基期量和增长率求现期量的公式是：现期量 = 基期量 × (1 + 增长率)。计算增长量时，若已知"
            "现期量和增长率，可以用增长量 = 现期量 × 增长率 / (1 + 增长率) 求得。当增长率较小且选项"
            "差距较大时，可以采用近似估算，例如把除法近似为乘以一个略小于1的数，以节省计算时间。"
            "资料分析题的关键是快速定位数据、准确列式、合理估算，而不是精确计算到小数点后多位。"
        ),
    },
    {
        "id": "s08",
        "domain": "医学",
        "title": "药物配伍禁忌中的十八反",
        "text": (
            "中药配伍禁忌中的十八反是一组传统的用药警戒，指某些药物配伍后可能产生毒性或降低疗效。"
            "十八反主要包含三类：甘草反甘遂、大戟、海藻、芫花；乌头反贝母、瓜蒌、半夏、白蔹、白及；"
            "藜芦反人参、沙参、丹参、玄参、细辛、芍药。因此有歌诀总结为：本草明言十八反，半蒌贝蔹及"
            "攻乌，藻戟遂芫俱战草，诸参辛芍叛藜芦。需要说明的是，十八反是古人经验的总结，其现代药理"
            "机制部分尚未完全明确，临床上对十八反的态度是谨慎使用而非绝对禁止，具体用药应遵循医师"
            "的处方和药典规定。"
        ),
    },
    {
        "id": "s09",
        "domain": "工程",
        "title": "三相异步电动机的工作原理",
        "text": (
            "三相异步电动机是利用电磁感应原理工作的。当三相定子绕组通入三相交流电后，会产生一个"
            "旋转磁场，转速称为同步转速，由电源频率和磁极对数决定，公式为 n1 = 60f / p。这个旋转"
            "磁场切割转子导体，在转子中产生感应电动势和感应电流，载流的转子导体在磁场中受到电磁力"
            "的作用，形成电磁转矩，驱动转子沿磁场方向旋转。转子转速 n 总是低于同步转速 n1，两者的"
            "差值称为转差，转差与同步转速之比称为转差率 s。如果转子达到同步转速，转子与磁场之间就"
            "没有相对运动，也就不会产生感应电流和电磁转矩，因此异步电动机的转速永远达不到同步转速。"
        ),
    },
    {
        "id": "s10",
        "domain": "经济",
        "title": "关税的经济效应",
        "text": (
            "关税是进口国对进口商品征收的一种税收。征收关税会带来几个直接效应：价格效应，进口商品的"
            "国内价格上升；消费效应，价格上涨导致国内消费量减少；生产效应，国内生产者因价格上升而"
            "增加产量；贸易效应，进口量下降；收入效应，政府获得关税收入。从福利角度看，关税使国内"
            "消费者剩余减少，国内生产者剩余和政府收入增加，但社会福利的净变化通常为负，因为产生了"
            "生产扭曲和消费扭曲两种效率损失，即所谓的无谓损失。此外，关税还会引起贸易转移和贸易"
            "报复，是国际贸易摩擦的常见起因。"
        ),
    },
    {
        "id": "s11",
        "domain": "统计",
        "title": "贝叶斯定理的直觉理解",
        "text": (
            "贝叶斯定理描述的是：在获得新证据之后，如何更新我们对某个假设的信念。公式为 P(A|B) = "
            "P(B|A) × P(A) / P(B)。其中 P(A) 是先验概率，即观察证据之前对假设的信念；P(B|A) 是似然，"
            "即在假设成立时观察到该证据的概率；P(A|B) 是后验概率，即观察到证据之后更新后的信念。"
            "一个经典例子是疾病筛查：某种罕见病的患病率为千分之一，检测的灵敏度为99%，假阳性率为5%。"
            "即使检测结果为阳性，实际患病的概率也只有约2%，因为先验概率极低，大量的假阳性稀释了"
            "阳性结果的诊断价值。这说明忽视基准率（base rate）是常见的认知偏误。"
        ),
    },
    {
        "id": "s12",
        "domain": "艺术",
        "title": "中国古典园林的造园手法",
        "text": (
            "中国古典园林讲究「虽由人作，宛自天开」，追求自然山水的意境。其核心造园手法包括："
            "叠山理水，用假山和池水模拟自然山水；借景，把园外的景色纳入园内视野，如颐和园借西山"
            "之景；框景，用门窗洞框取景色，使之成为一幅画面；对景，使两处景物互为观赏对象；"
            "障景，用山石花木遮挡视线，制造「欲扬先抑」的效果。空间处理上讲究曲折变化、步移景异，"
            "避免一览无余。中国古典园林分为皇家园林和私家园林两大类型，前者规模宏大、富丽堂皇，"
            "以颐和园、承德避暑山庄为代表；后者小巧精致、意境深远，以苏州拙政园、留园为代表。"
        ),
    },
    {
        "id": "s13",
        "domain": "心理学",
        "title": "认知失调理论",
        "text": (
            "认知失调理论由费斯廷格提出，指当一个人同时持有两个相互矛盾的认知（信念、态度或行为）时，"
            "会产生一种令人不适的紧张状态，这种状态就是认知失调。为了消除这种不适，人们会主动调整"
            "其中一个认知。费斯廷格的经典实验让被试做一小时极其枯燥的任务，然后要求他们向后来的"
            "被试谎称任务很有趣。得到1美元报酬的被试比得到20美元报酬的被试更倾向于真正认为任务有趣。"
            "解释是：拿1美元的人缺乏充分的外部理由来为自己撒谎辩护，只能通过改变内在态度"
            "（「任务其实挺有趣」）来减少失调；拿20美元的人有充足的外部理由，无需改变态度。这一理论解释了"
            "为什么人们会为自己付出努力的选择辩护。"
        ),
    },
    {
        "id": "s14",
        "domain": "IT",
        "title": "数据库索引的原理与代价",
        "text": (
            "数据库索引是一种加速数据检索的数据结构，最常见的是B+树索引。B+树的非叶子节点只存储键值"
            "和指针，叶子节点存储全部数据并通过链表相连，因此树的高度很低，通常三四层就能支撑千万级"
            "数据，一次查询只需少量磁盘I/O。叶子节点的链表结构也让范围查询非常高效。索引的代价有三："
            "一是占用额外的存储空间；二是插入、更新、删除数据时需要同步维护索引，降低写入性能；三是"
            "索引列上的函数运算或类型隐式转换会导致索引失效。因此索引并非越多越好，应根据实际查询"
            "模式建立。联合索引遵循最左前缀原则，查询条件必须从索引的最左列开始才能命中。"
        ),
    },
    {
        "id": "s15",
        "domain": "生物",
        "title": "蛋白质的合成过程",
        "text": (
            "蛋白质的合成包括转录和翻译两个主要阶段。转录发生在细胞核内，以DNA的一条链为模板，在"
            "RNA聚合酶的作用下合成信使RNA，即mRNA。真核生物的mRNA在转录后还需要经过加工，包括"
            "剪接去除内含子、加上5'端帽子结构和3'端polyA尾巴，然后通过核孔进入细胞质。翻译发生在"
            "核糖体上，mRNA上的每三个相邻碱基构成一个密码子，对应一种氨基酸，转运RNA即tRNA携带"
            "相应氨基酸进入核糖体，通过反密码子与密码子互补配对。核糖体沿mRNA从5'端向3'端移动，"
            "氨基酸之间形成肽键，逐步延长肽链，直到遇到终止密码子。"
        ),
    },
    {
        "id": "s16",
        "domain": "历史",
        "title": "萨拉热窝事件与一战爆发",
        "text": (
            "1914年6月28日，奥匈帝国皇储斐迪南大公夫妇在波斯尼亚首府萨拉热窝被塞尔维亚青年普林西普"
            "刺杀，这一事件成为第一次世界大战的导火索。但一战的爆发有着更深层的结构性原因：帝国主义"
            "国家之间政治经济发展不平衡，争夺殖民地和势力范围的矛盾日益尖锐；欧洲形成了德奥意三国"
            "同盟和英法俄三国协约两大军事集团，双方疯狂扩军备战；民族主义情绪高涨，巴尔干半岛被"
            "称为欧洲的火药桶。萨拉热窝事件后，奥匈在德国支持下向塞尔维亚宣战，各国因同盟条约相继"
            "卷入，一个月内演变为全欧洲的战争。这说明导火索事件只是引爆了早已积累的矛盾。"
        ),
    },
    {
        "id": "s17",
        "domain": "法律",
        "title": "有限责任公司股东的主要权利",
        "text": (
            "有限责任公司的股东享有多项法定权利。资产收益权是最基本的权利，股东按其出资比例分取红利，"
            "公司新增资本时有权优先认缴出资。参与重大决策权体现为股东会表决权，股东按出资比例行使"
            "表决权，但公司章程另有规定的除外。知情权允许股东查阅、复制公司章程、股东会会议记录、"
            "董事会决议、监事会决议和财务会计报告，也可以要求查阅公司会计账簿，但查阅会计账簿需要"
            "说明目的，公司有合理根据认为其有不正当目的时可以拒绝。选择管理者的权利体现为选举和"
            "更换董事、监事。此外还有异议股东回购请求权、剩余财产分配权以及在特定情形下提起股东"
            "代表诉讼的权利。"
        ),
    },
    {
        "id": "s18",
        "domain": "机器学习",
        "title": "过拟合与正则化",
        "text": (
            "过拟合指模型在训练数据上表现很好，但在未见过的测试数据上表现差，本质是模型学到了训练"
            "数据中的噪声和偶然规律，而没有学到真正的generalizable模式。过拟合的典型信号是训练误差"
            "持续下降而验证误差先降后升。造成过拟合的原因包括模型复杂度过高、训练样本太少、特征"
            "维度过多、训练轮次过多。常见的解决方案有：增加训练数据或做数据增强；降低模型复杂度；"
            "使用正则化，如L1正则化使部分权重变为零从而实现特征选择，L2正则化使权重整体变小；"
            "使用Dropout在训练时随机丢弃部分神经元；采用早停法在验证误差开始上升时停止训练；"
            "使用交叉验证更可靠地评估模型泛化能力。"
        ),
    },
    {
        "id": "s19",
        "domain": "英语",
        "title": "虚拟语气的三种时态",
        "text": (
            "虚拟语气用于表达与事实相反的假设、愿望或建议。在与现在事实相反的假设中，条件从句用"
            "一般过去时（be动词统一用were），主句用would/could/might加动词原形，例如：If I were you, "
            "I would accept the offer。在与过去事实相反的假设中，条件从句用过去完成时，主句用"
            "would/could/might have加过去分词，例如：If I had studied harder, I would have passed the exam。"
            "在与将来事实相反的假设中，条件从句用一般过去时或were to do或should do，主句用would加"
            "动词原形。此外，在表示建议、要求、命令的动词如suggest、demand、insist后的宾语从句中，"
            "谓语要用should加动词原形，且should可以省略。"
        ),
    },
    {
        "id": "s20",
        "domain": "管理",
        "title": "PDCA 循环",
        "text": (
            "PDCA循环是质量管理的基本方法，由美国质量管理专家戴明推广，因此也称戴明环。PDCA分别代表"
            "Plan计划、Do执行、Check检查、Act处理四个阶段。计划阶段要分析现状、找出问题、分析原因、"
            "确定要因、制定对策；执行阶段按计划实施；检查阶段对照计划检查执行效果，确认是否达到目标；"
            "处理阶段对成功的经验加以标准化和推广，对失败的教训进行总结，未解决的问题转入下一个循环。"
            "PDCA循环有两个特点：一是循环往复，每转一圈质量水平就提高一步，呈螺旋上升；二是大环带"
            "小环，整个组织的PDCA循环与各部门、各小组的循环协同运转、相互促进。"
        ),
    },
]


# --------------------------------------------------------------------------- #
# 提示词
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = (
    "你是一位资深教研专家，擅长把任意知识内容拆解为结构化、可判分、有教学价值的客观题。"
    "你只输出严格的 JSON，不输出任何解释、说明或 Markdown 代码块标记。"
)

USER_TEMPLATE = """请基于以下知识内容，生成一套用于闯关学习的题库。

【知识内容】
{text}

【输出要求】
严格输出 JSON，不要输出任何解释性文字，不要使用 Markdown 代码块包裹。
JSON 结构如下：
{{
  "outline": [
    {{"id": "kp1", "title": "知识点名称", "summary": "一句话说明该知识点的核心"}}
  ],
  "questions": [
    {{
      "id": "q1",
      "knowledge_point_id": "kp1",
      "type": "single",
      "difficulty": 2,
      "stem": "题干",
      "options": [{{"key": "A", "text": "选项内容"}}],
      "answer": ["A"],
      "explanation": "解释为什么这个答案正确，并说明其他选项错在哪里"
    }}
  ]
}}

【硬性约束】
1. outline 包含 3-5 个知识点，questions 包含 {min_q}-{max_q} 道题。
2. type 只能是 single（单选）、multiple（多选）、judge（判断）。
3. single 必须有 4 个选项且只有 1 个正确答案；multiple 必须有 4 个选项且至少 2 个正确答案；
   judge 固定 2 个选项（key 为 A、B），选项文本必须分别是"正确"和"错误"。
4. 严禁使用"以上都对""以上都不对"这类选项。
5. 每道题的 explanation 不少于 {min_explain} 个汉字，必须解释正确选项为什么正确。
6. difficulty 取 1-5 的整数，整套题目的难度要有梯度，不要全部相同。
7. 正确答案的分布要尽量均匀，不要全部集中在同一个选项。
8. 每道题的 knowledge_point_id 必须能在 outline 中找到。
9. 所有内容必须严格来自给定的知识内容，不得引入外部知识或编造事实。
10. 所有文本中禁止使用英文双引号 "，需要引用时一律使用中文引号「」，
    以免破坏 JSON 结构导致整份结果无法解析。
11. 输出必须是完整闭合的合法 JSON，不要在结尾被截断。
12. options 的 key 必须从 A 开始连续编号（A、B、C、D），不允许跳号或缺号；
    answer 只能引用已经给出的选项 key，绝不能引用不存在的选项。
    输出前请逐一自检：每个 answer 里的字母都能在该题的 options 中找到。
13. 语义不同的题目不要复用同一套选项，避免用户产生"又是这道题"的感觉。
"""


def build_prompt(text: str) -> str:
    return USER_TEMPLATE.format(
        text=text.strip(),
        min_q=MIN_QUESTIONS,
        max_q=MAX_QUESTIONS,
        min_explain=MIN_EXPLANATION_CHARS,
    )


# --------------------------------------------------------------------------- #
# 问题与结果的数据结构
# --------------------------------------------------------------------------- #


@dataclass
class Issue:
    severity: str          # "error" | "warn"
    code: str
    message: str
    where: str = ""        # 例如 "q3" 或 "outline"


@dataclass
class CaseResult:
    sample_id: str
    domain: str
    title: str
    ok: bool
    elapsed: float
    raw_text: str = ""
    payload: dict[str, Any] | None = None
    issues: list[Issue] = field(default_factory=list)
    error: str = ""
    parse_retries: int = 0

    @property
    def score(self) -> int:
        if self.error:
            return 0
        penalty = sum(PENALTY.get(i.severity, 0) for i in self.issues)
        return max(0, 100 - penalty)

    @property
    def n_error(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def n_warn(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warn")


# --------------------------------------------------------------------------- #
# 离线模拟数据（故意包含多种缺陷，用于验证检查器本身是否有效）
# --------------------------------------------------------------------------- #

MOCK_PAYLOAD_DEFECTIVE: dict[str, Any] = {
    "outline": [
        {"id": "kp1", "title": "货币政策的三大工具", "summary": "准备金率、再贴现率与公开市场操作"},
        {"id": "kp2", "title": "存款准备金率的作用机制", "summary": "通过影响可贷资金调节货币供应"},
        {"id": "kp3", "title": "公开市场操作的灵活性与方向", "summary": "买券投放、卖券回笼"},
    ],
    "questions": [
        {
            "id": "q1",
            "knowledge_point_id": "kp1",
            "type": "single",
            "difficulty": 3,
            "stem": "下列哪一项不属于中央银行调节货币供应量的三大传统工具？",
            "options": [
                {"key": "A", "text": "存款准备金率"},
                {"key": "B", "text": "再贴现率"},
                {"key": "C", "text": "公开市场操作"},
                {"key": "D", "text": "个人所得税税率"},
            ],
            "answer": ["D"],
            "explanation": (
                "个人所得税税率属于财政政策工具，由财政部门制定，直接影响居民可支配收入，"
                "而不是中央银行调节货币供应量的手段。存款准备金率、再贴现率和公开市场操作"
                "才是货币政策的三大传统工具。"
            ),
        },
        {
            "id": "q2",
            "knowledge_point_id": "kp2",
            "type": "single",
            "difficulty": 3,
            "stem": "当中央银行提高存款准备金率时，商业银行体系的可贷资金会发生什么变化？",
            "options": [
                {"key": "A", "text": "增加"},
                {"key": "B", "text": "减少"},
                {"key": "C", "text": "不变"},
                {"key": "D", "text": "先增加后减少"},
            ],
            "answer": ["E"],
            "explanation": (
                "提高准备金率意味着商业银行必须把更大比例的存款缴存央行，可用于放贷的资金随之减少，"
                "货币供应量收缩，因此属于紧缩性货币政策。"
            ),
        },
        {
            "id": "q3",
            "knowledge_point_id": "kp3",
            "type": "single",
            "difficulty": 3,
            "stem": "中央银行在公开市场上买入有价证券，会对基础货币产生什么影响？",
            "options": [
                {"key": "A", "text": "投放基础货币"},
                {"key": "B", "text": "回笼基础货币"},
                {"key": "C", "text": "投放基础货币"},
                {"key": "D", "text": "没有影响"},
            ],
            "answer": ["A"],
            "explanation": "买入证券会向市场投放基础货币，属于扩张性货币政策操作。",
        },
        {
            "id": "q4",
            "knowledge_point_id": "kp1",
            "type": "single",
            "difficulty": 3,
            "stem": "下列哪一项不属于中央银行调节货币供应量的三大传统工具？",
            "options": [
                {"key": "A", "text": "存款准备金率"},
                {"key": "B", "text": "再贴现率"},
                {"key": "C", "text": "公开市场操作"},
                {"key": "D", "text": "企业所得税税率"},
            ],
            "answer": ["D"],
            "explanation": "企业所得税税率属于财政政策工具，与中央银行调节货币供应量无关。",
        },
        {
            "id": "q5",
            "knowledge_point_id": "kp2",
            "type": "single",
            "difficulty": 3,
            "stem": "关于存款准备金率，下列说法正确的是？",
            "options": [
                {"key": "A", "text": "作用较为猛烈，通常不宜频繁使用"},
                {"key": "B", "text": "以上都对"},
                {"key": "C", "text": "是最灵活的工具"},
                {"key": "D", "text": "不会影响货币供应量"},
            ],
            "answer": ["A"],
            "explanation": (
                "存款准备金率的作用十分猛烈，被视为一剂猛药，通常不宜频繁使用。"
                "最灵活、使用最频繁的工具是公开市场操作，因此选项 C 错误。"
            ),
        },
        {
            "id": "q6",
            "knowledge_point_id": "kp3",
            "type": "judge",
            "difficulty": 3,
            "stem": "卖出有价证券属于扩张性货币政策操作。",
            "options": [
                {"key": "A", "text": "正确"},
                {"key": "B", "text": "错误"},
                {"key": "C", "text": "不确定"},
                {"key": "D", "text": "视情况而定"},
            ],
            "answer": ["B"],
            "explanation": (
                "卖出有价证券会回笼基础货币，减少市场流动性，属于紧缩性货币政策操作，"
                "而不是扩张性操作，因此题干说法错误。"
            ),
        },
        {
            "id": "q7",
            "knowledge_point_id": "kp9",
            "type": "single",
            "difficulty": 3,
            "stem": "三大货币政策工具中，哪一项使用最为频繁？",
            "options": [
                {"key": "A", "text": "存款准备金率"},
                {"key": "B", "text": "再贴现率"},
                {"key": "C", "text": "公开市场操作"},
                {"key": "D", "text": "窗口指导"},
            ],
            "answer": ["C"],
            "explanation": (
                "公开市场操作具有主动性强、灵活可逆、可以微调的特点，因此成为三大工具中"
                "使用最频繁的一种。窗口指导属于选择性的货币政策工具，不在三大传统工具之列。"
            ),
        },
        {
            "id": "q8",
            "knowledge_point_id": "kp1",
            "type": "multiple",
            "difficulty": 3,
            "stem": "下列哪些属于中央银行调节货币供应量的传统工具？",
            "options": [
                {"key": "A", "text": "存款准备金率"},
                {"key": "B", "text": "再贴现率"},
                {"key": "C", "text": "公开市场操作"},
                {"key": "D", "text": "政府转移支付"},
            ],
            "answer": ["A"],
            "explanation": (
                "存款准备金率、再贴现率和公开市场操作构成三大传统工具。政府转移支付属于"
                "财政政策，不属于货币政策工具。本题为多选题，正确答案应为 A、B、C。"
            ),
        },
    ],
}

# 一份"干净"的模拟数据：用于验证检查器在正常数据上不会误报。
MOCK_PAYLOAD_CLEAN: dict[str, Any] = {
    "outline": [
        {"id": "kp1", "title": "光的折射定律", "summary": "入射角与折射角的正弦比"},
        {"id": "kp2", "title": "全反射与临界角", "summary": "光密到光疏且超过临界角"},
        {"id": "kp3", "title": "光纤通信的应用", "summary": "利用全反射实现低损耗传输"},
    ],
    "questions": [
        {
            "id": "q1",
            "knowledge_point_id": "kp1",
            "type": "single",
            "difficulty": 1,
            "stem": "光从空气斜射入水中时，折射光线相对于入射光线会如何偏折？",
            "options": [
                {"key": "A", "text": "远离法线偏折"},
                {"key": "B", "text": "靠近法线偏折"},
                {"key": "C", "text": "沿原方向传播不偏折"},
                {"key": "D", "text": "沿原方向返回"},
            ],
            "answer": ["B"],
            "explanation": (
                "水相对于空气是光密介质，光从光疏介质进入光密介质时，折射角小于入射角，"
                "因此折射光线向法线靠拢。选项 A 描述的是相反情形，C 只在垂直入射时成立，"
                "D 描述的是反射而非折射。"
            ),
        },
        {
            "id": "q2",
            "knowledge_point_id": "kp1",
            "type": "single",
            "difficulty": 2,
            "stem": "根据折射定律，入射角的正弦与折射角的正弦之比等于什么？",
            "options": [
                {"key": "A", "text": "两种介质折射率之差"},
                {"key": "B", "text": "两种介质的密度之比"},
                {"key": "C", "text": "两种介质折射率之比"},
                {"key": "D", "text": "光在两种介质中的频率之比"},
            ],
            "answer": ["C"],
            "explanation": (
                "折射定律的数学表达为入射角正弦与折射角正弦之比等于两种介质折射率之比，"
                "比值恒为常数。密度之比与折射率并无必然相等关系，而光的频率在折射过程中"
                "保持不变，因此选项 A、B、D 均不正确。"
            ),
        },
        {
            "id": "q3",
            "knowledge_point_id": "kp2",
            "type": "single",
            "difficulty": 3,
            "stem": "发生全反射现象必须同时满足的条件是什么？",
            "options": [
                {"key": "A", "text": "光从光密介质射向光疏介质，且入射角大于临界角"},
                {"key": "B", "text": "光从光疏介质射向光密介质，且入射角大于临界角"},
                {"key": "C", "text": "光从光密介质射向光疏介质，且入射角小于临界角"},
                {"key": "D", "text": "只要入射角足够大，与介质类型无关"},
            ],
            "answer": ["A"],
            "explanation": (
                "全反射需要两个条件同时成立：一是光必须从光密介质射向光疏介质，二是入射角"
                "必须大于临界角。若从光疏射向光密介质，无论入射角多大都不会发生全反射，"
                "因此选项 B 与 D 错误；选项 C 中入射角小于临界角时仍会有折射光射出。"
            ),
        },
        {
            "id": "q4",
            "knowledge_point_id": "kp2",
            "type": "single",
            "difficulty": 4,
            "stem": "已知某介质对空气的临界角为45度，则光在该介质中的折射率约为多少？",
            "options": [
                {"key": "A", "text": "0.71"},
                {"key": "B", "text": "1.00"},
                {"key": "C", "text": "1.41"},
                {"key": "D", "text": "2.00"},
            ],
            "answer": ["C"],
            "explanation": (
                "临界角的正弦值等于光疏介质折射率与光密介质折射率之比，空气折射率取1，"
                "因此该介质的折射率等于临界角正弦值的倒数。45度角的正弦约为0.707，其倒数"
                "约为1.41，故正确选项是 C。"
            ),
        },
        {
            "id": "q5",
            "knowledge_point_id": "kp3",
            "type": "single",
            "difficulty": 3,
            "stem": "光纤通信能够实现长距离低损耗传输，主要依赖下列哪个光学现象？",
            "options": [
                {"key": "A", "text": "光的衍射"},
                {"key": "B", "text": "全反射"},
                {"key": "C", "text": "光的色散"},
                {"key": "D", "text": "光电效应"},
            ],
            "answer": ["B"],
            "explanation": (
                "光纤由折射率较高的纤芯和折射率较低的包层构成，光在纤芯中传播时如果入射角"
                "大于临界角，就会在纤芯与包层的界面上发生全反射，从而被约束在纤芯内不断向前"
                "传播，几乎没有能量泄漏，这正是低损耗传输的物理基础。"
            ),
        },
        {
            "id": "q6",
            "knowledge_point_id": "kp1",
            "type": "multiple",
            "difficulty": 2,
            "stem": "关于光的折射，下列说法正确的有哪些？",
            "options": [
                {"key": "A", "text": "入射光线、折射光线和法线在同一平面内"},
                {"key": "B", "text": "入射光线与折射光线分居法线两侧"},
                {"key": "C", "text": "光的频率在折射前后保持不变"},
                {"key": "D", "text": "光的波长在折射前后保持不变"},
            ],
            "answer": ["A", "B", "C"],
            "explanation": (
                "折射定律明确指出入射光线、折射光线和法线共面，且入射光线与折射光线分居"
                "法线两侧，因此 A、B 正确。光进入不同介质时频率由光源决定、保持不变，而"
                "传播速度改变，由速度等于波长乘频率可知波长必然改变，因此 D 错误。"
            ),
        },
        {
            "id": "q7",
            "knowledge_point_id": "kp2",
            "type": "judge",
            "difficulty": 5,
            "stem": "光从水中射向空气，当入射角达到临界角时，折射角等于90度。",
            "options": [
                {"key": "A", "text": "正确"},
                {"key": "B", "text": "错误"},
            ],
            "answer": ["A"],
            "explanation": (
                "临界角正是折射角等于90度时的入射角，此时折射光线恰好沿着两种介质的界面"
                "掠过。入射角一旦超过临界角，折射光完全消失，进入全反射状态，因此题干表述"
                "符合临界角的定义。"
            ),
        },
        {
            "id": "q8",
            "knowledge_point_id": "kp3",
            "type": "judge",
            "difficulty": 4,
            "stem": "光纤的包层折射率应当大于纤芯折射率，才能保证光被约束在纤芯中传播。",
            "options": [
                {"key": "A", "text": "正确"},
                {"key": "B", "text": "错误"},
            ],
            "answer": ["B"],
            "explanation": (
                "要实现全反射，光必须从光密介质射向光疏介质，因此纤芯折射率必须大于包层"
                "折射率，光才能在两者界面上发生全反射而被约束在纤芯内。题干把大小关系说反"
                "了，故该说法错误。"
            ),
        },
    ],
}

# 离线模式下依次使用的模拟数据：(样例索引, 模拟返回)
MOCK_SEQUENCE: list[tuple[dict[str, str], dict[str, Any]]] = [
    (SAMPLES[0], MOCK_PAYLOAD_DEFECTIVE),
    (SAMPLES[1], MOCK_PAYLOAD_CLEAN),
]


# --------------------------------------------------------------------------- #
# 大模型调用
# --------------------------------------------------------------------------- #


def load_dotenv(path: Path) -> dict[str, str]:
    """极简 .env 解析器，不依赖任何第三方库。

    支持：# 注释、空行、export 前缀、KEY=VALUE、
    值被引号包裹、行尾以 " #" 开头的注释。
    """
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError:
        return result

    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        if key:
            result[key] = value
    return result


def load_env_files() -> list[str]:
    """加载 .env 文件到 os.environ。

    查找顺序：脚本所在目录的 .env → 当前工作目录的 .env。
    已存在的系统环境变量优先，不会被 .env 覆盖。
    返回实际加载到的文件路径列表。
    """
    candidates = [
        Path(__file__).resolve().parent / ".env",
        Path.cwd() / ".env",
    ]
    loaded: list[str] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        data = load_dotenv(resolved)
        if not data:
            continue
        for key, value in data.items():
            if value and not os.environ.get(key):
                os.environ[key] = value
        loaded.append(str(resolved))
    return loaded


def resolve_api_key() -> str:
    """按优先级取 API Key：环境变量优先，其次 .env，最后通用名。"""
    for name in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def mask_key(key: str) -> str:
    """脱敏显示，避免把完整密钥打印到屏幕或日志里。"""
    if len(key) <= 10:
        return key[:2] + "*" * max(0, len(key) - 2)
    return f"{key[:6]}{'*' * 6}{key[-4:]}"


def looks_like_placeholder(key: str) -> bool:
    """识别 .env.example 里的占位符，避免用户忘了替换就运行。"""
    lowered = key.lower()
    markers = ("xxxx", "your", "你的", "placeholder", "填入", "替换")
    return any(m in lowered for m in markers)


def call_llm(prompt: str, *, api_key: str, base_url: str, model: str,
             timeout: int = DEFAULT_TIMEOUT, retries: int = 2) -> str:
    """调用 OpenAI 兼容接口，返回原始文本。"""
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:            # noqa: PERF203
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:                            # pragma: no cover
                pass
            last_err = RuntimeError(f"HTTP {exc.code}: {detail}")
            # 4xx（除 429）通常重试也没用，直接失败
            if 400 <= exc.code < 500 and exc.code != 429:
                raise last_err from exc
        except Exception as exc:                         # noqa: BLE001
            last_err = exc
        if attempt < retries:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"调用大模型失败：{last_err}")


def extract_json(text: str) -> dict[str, Any]:
    """从模型返回中稳健地抽取 JSON。

    大模型输出的 JSON 经常有瑕疵：被代码块包裹、前后有说明文字、
    结尾多一个逗号、内容过长被截断。这里逐级降级尝试修复，
    尽量避免"明明生成了内容却报解析失败"。
    """
    if not text or not text.strip():
        raise ValueError("模型返回为空")
    cleaned = text.strip()
    # 去掉 ```json ... ``` 包裹
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()

    # 第 1 级：直接解析 / 去掉尾逗号后解析
    for candidate in (cleaned, _strip_trailing_commas(cleaned)):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # 第 2 级：截取第一个 { 到最后一个 }
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(_strip_trailing_commas(cleaned[start:end + 1]))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # 第 3 级：截断修复（在最后一个完整的元素边界处闭合括号）
    repaired = repair_json(cleaned)
    if repaired is not None:
        return repaired

    raise ValueError("无法从返回内容中解析出 JSON")


def _strip_trailing_commas(s: str) -> str:
    """去掉对象/数组结尾多余逗号：{"a":1,} -> {"a":1}"""
    return re.sub(r",(\s*[}\]])", r"\1", s)


def _balance_and_close(s: str) -> str | None:
    """在字符串状态正常的前提下，为未闭合的括号补上结尾。

    如果扫描结束时正处于字符串内部，说明是"截断在半个字符串里"，
    无法安全修复，返回 None。
    """
    stack: list[str] = []
    in_str = False
    escaped = False
    for ch in s:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            if not stack:
                return None
            stack.pop()
    if in_str:
        return None
    return s + "".join("]" if c == "[" else "}" for c in reversed(stack))


def repair_json(text: str) -> dict[str, Any] | None:
    """尝试修复被截断的 JSON：从后往前找最后一个元素边界，补齐括号。"""
    start = text.find("{")
    if start == -1:
        return None
    body = text[start:]

    positions = [m.end() for m in re.finditer(r"[}\]]", body)]
    for pos in reversed(positions[-150:]):
        closed = _balance_and_close(_strip_trailing_commas(body[:pos]))
        if not closed:
            continue
        try:
            data = json.loads(closed)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


# --------------------------------------------------------------------------- #
# 质量检查
# --------------------------------------------------------------------------- #


def _norm(text: Any) -> str:
    """归一化文本，用于相似度与重复判断。"""
    s = str(text or "")
    s = re.sub(r"[\s\u3000]+", "", s)
    s = re.sub(r"[，。、；：？！,.;:?!（）()\[\]【】\"'“”‘’]", "", s)
    return s


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _set_overlap(a: list[str], b: list[str]) -> float:
    """两个选项集合的重合度：交集大小 / 较大集合大小。"""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(len(sa), len(sb))


def _is_low_quality_option(text: str) -> bool:
    t = _norm(text)
    return any(re.search(p, t) for p in LOW_QUALITY_OPTION_PATTERNS)


def audit_case(payload: dict[str, Any]) -> list[Issue]:
    """对一次生成结果做全面质量检查。"""
    issues: list[Issue] = []

    def err(code: str, msg: str, where: str = "") -> None:
        issues.append(Issue("error", code, msg, where))

    def warn(code: str, msg: str, where: str = "") -> None:
        issues.append(Issue("warn", code, msg, where))

    # ---------- 1. 顶层结构 ----------
    outline = payload.get("outline")
    questions = payload.get("questions")
    if not isinstance(outline, list) or not outline:
        err("outline_missing", "缺少 outline 或 outline 为空")
        outline = []
    if not isinstance(questions, list) or not questions:
        err("questions_missing", "缺少 questions 或 questions 为空")
        return issues

    kp_ids: set[str] = set()
    for idx, kp in enumerate(outline, 1):
        if not isinstance(kp, dict):
            err("kp_malformed", f"第 {idx} 个知识点不是对象", f"kp{idx}")
            continue
        kid = str(kp.get("id", "")).strip()
        if not kid:
            err("kp_id_missing", f"第 {idx} 个知识点缺少 id", f"kp{idx}")
        else:
            if kid in kp_ids:
                err("kp_id_dup", f"知识点 id 重复：{kid}", f"kp{idx}")
            kp_ids.add(kid)
        if not str(kp.get("title", "")).strip():
            err("kp_title_missing", f"知识点 {kid or idx} 缺少 title", f"kp{idx}")

    if len(outline) < 3:
        warn("outline_too_few", f"知识点只有 {len(outline)} 个，建议 3-5 个")
    if len(outline) > 5:
        warn("outline_too_many", f"知识点有 {len(outline)} 个，建议 3-5 个")

    # ---------- 2. 题目数量 ----------
    n = len(questions)
    if n < MIN_QUESTIONS:
        warn("questions_too_few", f"题目只有 {n} 道，少于目标下限 {MIN_QUESTIONS}")
    if n > MAX_QUESTIONS:
        warn("questions_too_many", f"题目有 {n} 道，多于目标上限 {MAX_QUESTIONS}")

    # ---------- 3. 逐题检查 ----------
    # 每道题一条记录：where / stem(归一化) / opts(归一化) / type
    # 用于跨题检查（重复、并列考察等）
    records: list[dict[str, Any]] = []
    single_answers: list[str] = []
    difficulties: list[int] = []
    used_kps: set[str] = set()

    for idx, q in enumerate(questions, 1):
        where = f"q{idx}"
        if not isinstance(q, dict):
            err("q_malformed", f"第 {idx} 题不是对象", where)
            continue

        qid = str(q.get("id", "") or where)

        # 必填字段
        for field_name in ("type", "stem", "options", "answer", "explanation"):
            if q.get(field_name) in (None, "", [], {}):
                err("field_missing", f"缺少必填字段 {field_name}", where)

        # 知识点关联
        kp_ref = str(q.get("knowledge_point_id", "")).strip()
        if not kp_ref:
            err("kp_ref_missing", "未关联知识点 knowledge_point_id", where)
        elif kp_ref not in kp_ids:
            err("kp_ref_invalid", f"关联的知识点 {kp_ref} 不存在于 outline 中", where)
        else:
            used_kps.add(kp_ref)

        # 题型
        qtype = str(q.get("type", "")).strip().lower()
        if qtype not in VALID_TYPES:
            err("type_invalid", f"题型非法：{qtype!r}", where)

        # 难度
        diff = q.get("difficulty")
        if not isinstance(diff, int) or not (1 <= diff <= 5):
            warn("difficulty_invalid", f"难度值非法或缺失：{diff!r}", where)
        else:
            difficulties.append(diff)

        # 题干
        stem = str(q.get("stem", "")).strip()
        stem_norm = _norm(stem)
        if stem:
            # 判断题的题干本身就是一句简短陈述，不适用"题干过短"的下限；
            # 单选题里"XX是指？"这类定义型题干也很短，同样属于正常写法。
            if qtype != "judge" and len(stem) < MIN_STEM_CHARS:
                warn("stem_too_short", f"题干过短（{len(stem)} 字）", where)
            if len(stem) > MAX_STEM_CHARS:
                warn("stem_too_long", f"题干过长（{len(stem)} 字）", where)

        # 选项
        options = q.get("options")
        if not isinstance(options, list) or not options:
            err("options_missing", "options 缺失或为空", where)
            continue

        keys: list[str] = []
        texts: list[str] = []
        for oi, opt in enumerate(options, 1):
            if not isinstance(opt, dict):
                err("option_malformed", f"第 {oi} 个选项不是对象", where)
                continue
            k = str(opt.get("key", "")).strip()
            t = str(opt.get("text", "")).strip()
            if not k:
                err("option_key_missing", f"第 {oi} 个选项缺少 key", where)
            if not t:
                err("option_text_missing", f"选项 {k or oi} 的 text 为空", where)
            keys.append(k)
            texts.append(t)

        if len(set(keys)) != len(keys):
            err("option_key_dup", "选项 key 有重复", where)
        if len(set(texts)) != len(texts):
            err("option_text_dup", "存在内容完全相同的选项", where)

        norm_texts = [_norm(t) for t in texts if t]
        # 注意：这里刻意不做"选项高度相似"的检查。
        # 题意相近、只差一两个字的"最小对照选项"（如把「光密射向光疏」改成
        # 「光疏射向光密」）是优秀的干扰项设计，用于考察精确理解，
        # 自动判相似度会把好题误判为缺陷。只保留"完全相同"的硬性错误。

        for t in texts:
            if _is_low_quality_option(t):
                err("option_low_quality",
                    f"使用了低质量选项（如「{t}」），教研上视为无效干扰项", where)

        # 题型与选项数量一致性
        if qtype == "single" and len(options) != 4:
            err("single_option_count", f"单选题应有 4 个选项，实际 {len(options)} 个", where)
        if qtype == "multiple" and len(options) < 4:
            err("multiple_option_count", f"多选题至少应有 4 个选项，实际 {len(options)} 个", where)
        if qtype == "judge":
            if len(options) != 2:
                err("judge_option_count", f"判断题应只有 2 个选项，实际 {len(options)} 个", where)
            else:
                for t in texts:
                    if _norm(t).lower() not in {_norm(x).lower() for x in JUDGE_OPTION_TEXTS}:
                        warn("judge_option_text",
                             f"判断题选项文本建议为「正确/错误」，当前为「{t}」", where)
                        break

        # 答案
        answer = q.get("answer")
        if not isinstance(answer, list) or not answer:
            err("answer_invalid", "answer 必须是非空数组", where)
        else:
            ans_keys = [str(a).strip() for a in answer]
            for a in ans_keys:
                if a not in keys:
                    err("answer_not_in_options",
                        f"答案 {a} 不在选项 {keys} 中", where)
            if qtype in ("single", "judge") and len(ans_keys) != 1:
                err("answer_count_mismatch",
                    f"{qtype} 题型应只有 1 个正确答案，实际 {len(ans_keys)} 个", where)
            if qtype == "multiple" and len(ans_keys) < 2:
                err("answer_count_mismatch",
                    f"多选题至少应有 2 个正确答案，实际 {len(ans_keys)} 个", where)
            if qtype == "single" and len(ans_keys) == 1:
                single_answers.append(ans_keys[0])

        # 讲解
        explanation = str(q.get("explanation", "")).strip()
        if not explanation:
            err("explanation_missing", "缺少讲解", where)
        elif len(explanation) < 20:
            err("explanation_too_short",
                f"讲解极短（{len(explanation)} 字），几乎没有教学价值", where)
        elif len(explanation) < MIN_EXPLANATION_CHARS:
            warn("explanation_too_short",
                 f"讲解过短（{len(explanation)} 字，建议不少于 {MIN_EXPLANATION_CHARS} 字）", where)

        # 讲解中断言的答案与 answer 字段是否一致
        # 真实缺陷形如：讲解写"正确答案应为 A、B、C"，answer 却只有 A
        # 注意：解释错误选项（"故不选D""若选B则相反"）不算不一致
        if explanation and isinstance(answer, list) and answer:
            asserted = extract_asserted_answers(explanation)
            ans_set = {str(a).strip() for a in answer}
            wrong = sorted({k for k in asserted if k not in ans_set})
            if wrong:
                err("explanation_answer_mismatch",
                    f"讲解中断言答案为 {'、'.join(wrong)}，但 answer 字段是 "
                    f"{'、'.join(sorted(ans_set))}，两者不一致", where)

        records.append({"where": where, "stem": stem_norm,
                        "opts": norm_texts, "type": qtype})

    # ---------- 4. 跨题检查：重复 ----------
    # 重要：题干"句式相同"不等于"题目重复"。
    # 例如「求基期量的公式是？」与「求增长量的公式是？」这类同一模板下考察
    # 不同知识点的并列出题，是优秀的教学设计（便于对比记忆）。
    # 早期版本仅凭文本相似度判断，把它们全部误报成了重复。
    # 现在要求"题干相似"与"选项重合"同时成立，才算真正的重复题。
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            ra, rb = records[i], records[j]
            if not ra["stem"] or not rb["stem"]:
                continue
            stem_ratio = _similar(ra["stem"], rb["stem"])
            if stem_ratio < DUPLICATE_STEM_RATIO:
                continue
            opt_ratio = _set_overlap(ra["opts"], rb["opts"])
            if opt_ratio >= DUPLICATE_OPTION_OVERLAP:
                err("stem_duplicate",
                    f"{ra['where']} 与 {rb['where']}：题干相似度 {stem_ratio:.0%}、"
                    f"选项重合度 {opt_ratio:.0%}，基本属于同一道题", rb["where"])

    # 选项组完全相同：同一套选项被 3 道及以上题目复用时才算缺陷。
    # 只有 2 道题共用选项组，通常是对同一组概念从不同角度的考察，属于正常设计。
    option_group: dict[tuple[str, ...], list[str]] = {}
    for r in records:
        if r["type"] == "judge" or not r["opts"]:
            continue          # 判断题选项固定为「正确/错误」，必然相同
        option_group.setdefault(tuple(r["opts"]), []).append(r["where"])
    for _group, wheres in option_group.items():
        if len(wheres) >= 3:
            warn("option_set_duplicate",
                 f"{'、'.join(wheres)} 这 {len(wheres)} 道题使用了完全相同的选项组，"
                 f"建议让选项更有区分度", wheres[-1])

    # ---------- 5. 答案分布 ----------
    if len(single_answers) >= 4:
        counts: dict[str, int] = {}
        for a in single_answers:
            counts[a] = counts.get(a, 0) + 1
        top_key, top_n = max(counts.items(), key=lambda kv: kv[1])
        ratio = top_n / len(single_answers)
        if ratio > ANSWER_SKEW_RATIO:
            warn("answer_skew",
                 f"单选题答案分布不均：选项 {top_key} 占比 {ratio:.0%}"
                 f"（共 {len(single_answers)} 道单选题）")

    # ---------- 6. 难度梯度 ----------
    if difficulties and len(set(difficulties)) == 1:
        warn("difficulty_flat", f"所有题目难度相同（均为 {difficulties[0]}），缺少梯度")

    # ---------- 7. 知识点覆盖 ----------
    uncovered = kp_ids - used_kps
    if uncovered:
        warn("kp_uncovered", f"以下知识点没有任何题目覆盖：{', '.join(sorted(uncovered))}")

    return issues


# --------------------------------------------------------------------------- #
# 单例执行
# --------------------------------------------------------------------------- #


def run_case(sample: dict[str, str], *, mock: bool = False,
             mock_payload: dict[str, Any] | None = None,
             api_key: str = "", base_url: str = "", model: str = "",
             dry_run: bool = False) -> CaseResult:
    result = CaseResult(
        sample_id=sample["id"],
        domain=sample["domain"],
        title=sample["title"],
        ok=False,
        elapsed=0.0,
    )
    if dry_run:
        result.error = "DRY_RUN"
        return result

    started = time.time()
    try:
        if mock:
            source = mock_payload if mock_payload is not None else MOCK_PAYLOAD_DEFECTIVE
            payload = json.loads(json.dumps(source))         # 深拷贝
            result.raw_text = json.dumps(payload, ensure_ascii=False)
        else:
            # 大模型偶尔会返回不合法 JSON（引号未转义、输出被截断等）。
            # 这里解析失败就重试，避免"明明生成了内容却整份作废"。
            prompt = build_prompt(sample["text"])
            payload: dict[str, Any] | None = None
            last_err: Exception | None = None
            for attempt in range(PARSE_RETRIES + 1):
                raw = call_llm(prompt, api_key=api_key, base_url=base_url, model=model)
                result.raw_text = raw
                try:
                    payload = extract_json(raw)
                    result.parse_retries = attempt
                    break
                except Exception as exc:                     # noqa: BLE001
                    last_err = exc
                    result.parse_retries = attempt
                    if attempt < PARSE_RETRIES:
                        time.sleep(1.5)
            if payload is None:
                raise ValueError(
                    f"连续 {PARSE_RETRIES + 1} 次返回均无法解析为 JSON：{last_err}"
                ) from last_err
        result.payload = payload
        result.issues = audit_case(payload)
        result.ok = True
    except Exception as exc:                                  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
        result.issues = [Issue("error", "generation_failed", result.error)]
    result.elapsed = time.time() - started
    return result


# --------------------------------------------------------------------------- #
# 报告渲染
# --------------------------------------------------------------------------- #


def render_markdown(results: list[CaseResult], meta: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append

    add("# AI 出题质量检测报告")
    add("")
    add(f"- 生成时间：{meta['generated_at']}")
    add(f"- 运行模式：{meta['mode']}")
    add(f"- 模型：{meta['model']}")
    add(f"- 样例数量：{len(results)}")
    add("")
    if meta.get("aborted_reason"):
        add(f"> ⚠️ **本次运行被提前中止**：{str(meta['aborted_reason'])[:200]}")
        add("> 剩余样例未执行，下面的生成成功率与平均分只反映已执行的部分。")
        add("")

    # ---------- 汇总 ----------
    # 只统计"成功生成"的样例。生成失败单独用成功率体现，
    # 不混进平均分里（否则一个失败会把平均值拉低一大截，掩盖真实质量）。
    scored = [r for r in results if r.payload is not None]
    success = len(scored)
    avg = sum(r.score for r in scored) / len(scored) if scored else 0.0
    total_err = sum(r.n_error for r in results)
    total_warn = sum(r.n_warn for r in results)
    passed = sum(1 for r in results if r.ok and r.n_error == 0)

    add("## 1. 总览")
    add("")
    add("| 指标 | 数值 |")
    add("| --- | --- |")
    add(f"| 生成成功率 | {success} / {len(results)} （{success / len(results):.0%}） |")
    add(f"| 平均得分（仅成功样例） | {avg:.1f} / 100 |")
    add(f"| 零错误样例数 | {passed} / {len(results)} |")
    add(f"| 错误总数 | {total_err} |")
    add(f"| 警告总数 | {total_warn} |")
    add(f"| 平均耗时 | {sum(r.elapsed for r in results) / len(results):.1f} 秒 |")
    retries = sum(r.parse_retries for r in results)
    if retries or meta["mode"] != "离线模拟":
        add(f"| JSON 解析自动重试 | {retries} 次 |")
    add("")

    if total_err == 0 and total_warn == 0 and meta["mode"] != "离线模拟":
        add("> 全部样例未发现问题。但请注意：自动检查只能发现**结构性缺陷**，"
            "题目在事实上是否准确、是否存在歧义，仍需人工抽检。")
        add("")

    # ---------- 明细表 ----------
    add("## 2. 各样例结果")
    add("")
    add("| 样例 | 领域 | 主题 | 题目数 | 错误 | 警告 | 得分 | 耗时(s) |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in results:
        nq = len(r.payload.get("questions", [])) if isinstance(r.payload, dict) else 0
        status = "❌ 生成失败" if r.error and r.error != "DRY_RUN" else str(r.score)
        add(f"| {r.sample_id} | {r.domain} | {r.title} | {nq} | {r.n_error} | "
            f"{r.n_warn} | {status} | {r.elapsed:.1f} |")
    add("")

    # ---------- 问题类型排行 ----------
    code_counter: dict[str, int] = {}
    severity_of: dict[str, str] = {}
    for r in results:
        for i in r.issues:
            code_counter[i.code] = code_counter.get(i.code, 0) + 1
            severity_of[i.code] = i.severity

    if code_counter:
        add("## 3. 问题类型分布")
        add("")
        add("| 问题代码 | 级别 | 出现次数 |")
        add("| --- | --- | --- |")
        for code, cnt in sorted(code_counter.items(), key=lambda kv: -kv[1]):
            level = "错误" if severity_of.get(code) == "error" else "警告"
            add(f"| {code} | {level} | {cnt} |")
        add("")

    # ---------- 逐条明细 ----------
    add("## 4. 问题明细")
    add("")
    for r in results:
        if r.error and r.error != "DRY_RUN":
            add(f"### {r.sample_id} · {r.title} — 生成失败")
            add("")
            add("```")
            add(r.error)
            add("```")
            add("")
            continue
        if not r.issues:
            continue
        add(f"### {r.sample_id} · {r.title}（得分 {r.score}）")
        add("")
        for i in r.issues:
            tag = "🔴 错误" if i.severity == "error" else "🟡 警告"
            loc = f" `{i.where}`" if i.where else ""
            add(f"- {tag}{loc} `{i.code}` — {i.message}")
        add("")

    # ---------- 建议 ----------
    add("## 5. 结论与下一步建议")
    add("")
    if meta["mode"] == "离线模拟":
        add("本次为**离线模拟运行**，使用的是内置的、故意包含缺陷的样例数据，"
            "目的是验证脚本自身的检查逻辑是否正常工作。")
        add("")
        add("请设置 API Key 后运行真实模式：")
        add("")
        add("```bash")
        add("set DEEPSEEK_API_KEY=sk-xxxxxxxx          # Windows CMD")
        add("$env:DEEPSEEK_API_KEY=\"sk-xxxxxxxx\"       # Windows PowerShell")
        add("export DEEPSEEK_API_KEY=sk-xxxxxxxx       # macOS / Linux")
        add("python quality_check.py --limit 3          # 先跑 3 个样例试水")
        add("```")
        add("")
    else:
        if total_err == 0 and total_warn == 0:
            add("自动检查未发现结构性问题。建议继续进行**人工抽检**：")
        else:
            add("自动检查发现了问题。建议按以下顺序处理：")
        add("")
        add("1. **先看错误，再看警告。** 错误（如答案不在选项中、选项重复）会直接摧毁"
            "用户体验，必须优先修复提示词。")
        add("2. **人工抽检事实准确性。** 自动检查无法判断题目内容是否符合原文、"
            "是否存在歧义——这是最需要人工判断的部分，建议每个样例抽 3 道题逐题核对。")
        add("3. **记录修复前后的得分变化。** 每次调整提示词后重跑，用平均分衡量改进效果，"
            "不要凭感觉判断提示词好坏。")
        add("4. **把高频错误写入提示词的硬性约束。** 例如反复出现「以上都对」，"
            "就在提示词里点名禁止。")

    add("")
    add("---")
    add("")
    add("## 附：如何解读这些检查项")
    add("")
    add("| 检查项 | 为什么重要 |")
    add("| --- | --- |")
    add("| answer_not_in_options | 答案不在选项里，用户永远答不对，属致命缺陷 |")
    add("| option_text_dup | 选项重复，题目实际上没有唯一解 |")
    add("| option_low_quality | 「以上都对」这类选项无法考察理解，是无效干扰项 |")
    add("| stem_duplicate | 重复出题会让用户觉得产品粗糙，也浪费生成成本 |")
    add("| answer_skew | 答案集中在同一个选项，用户会靠猜规律而非理解作答 |")
    add("| difficulty_flat | 没有难度梯度就构不成「闯关」，心流体验会失效 |")
    add("| explanation_too_short | 讲解是核心价值，太短等于没有教学效果 |")
    add("| kp_uncovered | 有知识点没出题，闯关进度与学习目标对不上 |")
    add("")
    add("*报告由 quality_check.py 自动生成*")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# 命令行入口
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AI 出题质量检测脚本：验证「输入文字 → AI 出题」的质量",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--mock", action="store_true",
                     help="离线模式：使用内置模拟数据，不调用 API")
    src.add_argument("--text", type=str, default=None,
                     help="直接传入一段知识文本")
    src.add_argument("--file", type=str, default=None,
                     help="从文本文件读取知识内容")
    p.add_argument("--limit", type=int, default=None,
                   help="只跑前 N 个内置样例（默认全部 20 个）")
    p.add_argument("--outdir", type=str, default=DEFAULT_OUTDIR,
                   help="报告输出目录（默认为脚本同级的 reports/）")
    p.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL,
                   help=f"API Base URL（默认 {DEFAULT_BASE_URL}）")
    p.add_argument("--model", type=str, default=DEFAULT_MODEL,
                   help=f"模型名（默认 {DEFAULT_MODEL}）")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印将要发送的提示词，不调用 API")
    p.add_argument("--reaudit", type=str, default=None, metavar="RAW_JSON",
                   help="对已有的 raw_*.json 重新评分（不调用 API，"
                        "用于验证检查规则改动后的效果）")
    p.add_argument("--version", action="version", version=f"quality_check {VERSION}")
    return p.parse_args(argv)


def collect_samples(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.text:
        return [{"id": "custom1", "domain": "自定义", "title": "自定义文本",
                 "text": args.text}]
    if args.file:
        path = Path(args.file)
        if not path.exists():
            raise SystemExit(f"文件不存在：{path}")
        content = path.read_text(encoding="utf-8")
        return [{"id": "file1", "domain": "自定义", "title": path.stem,
                 "text": content}]
    samples = list(SAMPLES)
    if args.limit:
        samples = samples[: max(0, args.limit)]
    return samples


# --------------------------------------------------------------------------- #
# 重新评分：用新的检查规则重算历史结果（不调用 API，不花钱）
# --------------------------------------------------------------------------- #


def _result_from_dump_item(item: dict[str, Any], domain: str) -> CaseResult:
    """把 raw_*.json 里的一条记录还原成 CaseResult。"""
    r = CaseResult(
        sample_id=str(item.get("sample_id", "")),
        domain=domain,
        title=str(item.get("title", "")),
        ok=False,
        elapsed=float(item.get("elapsed", 0.0) or 0.0),
        raw_text=str(item.get("raw_text", "") or ""),
        payload=item.get("payload"),
        error=str(item.get("error", "") or ""),
        parse_retries=int(item.get("parse_retries", 0) or 0),
    )
    r.issues = [
        Issue(str(i.get("severity", "warn")), str(i.get("code", "")),
              str(i.get("message", "")), str(i.get("where", "") or ""))
        for i in (item.get("issues") or [])
    ]
    return r


def _score_label(r: CaseResult) -> str:
    if r.payload is None:
        return "生成失败"
    return str(r.score)


def reaudit(raw_path: Path, outdir: Path) -> int:
    """用当前的检查规则，对历史检测结果重新评分。

    用途：调整检查规则后，不必再花钱重新调用大模型，
    直接对上次的原始结果重新算分，就能看出规则改动的效果。
    """
    if not raw_path.is_file():
        print(f"[错误] 找不到文件：{raw_path}", file=sys.stderr)
        return 1

    data = json.loads(raw_path.read_text(encoding="utf-8"))
    samples = {s.get("id"): s for s in data.get("samples", [])}

    old_results: list[CaseResult] = []
    new_results: list[CaseResult] = []
    for item in data.get("results", []):
        sid = str(item.get("sample_id", ""))
        domain = str(samples.get(sid, {}).get("domain", ""))

        old_results.append(_result_from_dump_item(item, domain))

        new = _result_from_dump_item(item, domain)
        new.parse_retries = 0
        new.issues = []
        if item.get("payload"):
            new.ok = True
            new.issues = audit_case(item["payload"])
        else:
            new.ok = False
            new.issues = [Issue("error", "generation_failed",
                                new.error or "生成失败")]
        new_results.append(new)

    def summarize(rs: list[CaseResult]) -> tuple[float, int, int]:
        scored = [r for r in rs if r.payload is not None]
        avg = sum(r.score for r in scored) / len(scored) if scored else 0.0
        return avg, sum(r.n_error for r in rs), sum(r.n_warn for r in rs)

    o_avg, o_err, o_warn = summarize(old_results)
    n_avg, n_err, n_warn = summarize(new_results)

    print("=" * 76)
    print("重新评分（不调用 API，仅用当前检查规则重算历史结果）")
    print("=" * 76)
    print(f"数据来源：{raw_path}")
    print()
    print(f"{'样例':<6}{'主题':<26}{'旧得分':>9}{'新得分':>9}   变化")
    print("-" * 76)
    changes = 0
    for o, n in zip(old_results, new_results):
        delta = ""
        if o.payload is not None and n.payload is not None:
            d = n.score - o.score
            if d:
                delta = f"+{d}" if d > 0 else str(d)
                changes += 1
            else:
                delta = "—"
        print(f"{o.sample_id:<6}{o.title[:22]:<26}"
              f"{_score_label(o):>9}{_score_label(n):>9}   {delta}")
    print("-" * 76)
    print(f"{'平均':<32}{o_avg:>9.1f}{n_avg:>9.1f}"
          f"   {'+' if n_avg > o_avg else ''}{n_avg - o_avg:.1f}")
    print(f"{'错误数':<32}{o_err:>9}{n_err:>9}")
    print(f"{'警告数':<32}{o_warn:>9}{n_warn:>9}")
    print("-" * 76)
    print(f"共 {changes} 个样例的得分发生变化")
    print()

    # 输出对比报告
    lines = [
        "# 检查规则调整 · 重新评分对比",
        "",
        f"- 数据来源：`{raw_path}`",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 说明：不调用大模型，仅用调整后的检查规则对历史结果重新评分",
        "",
        "## 1. 总体对比",
        "",
        "| 指标 | 调整前 | 调整后 | 变化 |",
        "| --- | --- | --- | --- |",
        f"| 平均得分 | {o_avg:.1f} | {n_avg:.1f} | "
        f"{'+' if n_avg > o_avg else ''}{n_avg - o_avg:.1f} |",
        f"| 错误总数 | {o_err} | {n_err} | {n_err - o_err} |",
        f"| 警告总数 | {o_warn} | {n_warn} | {n_warn - o_warn} |",
        "",
        "## 2. 逐样例对比",
        "",
        "| 样例 | 主题 | 调整前 | 调整后 | 变化 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for o, n in zip(old_results, new_results):
        delta = "—"
        if o.payload is not None and n.payload is not None:
            d = n.score - o.score
            delta = f"+{d}" if d > 0 else (str(d) if d else "—")
        lines.append(f"| {o.sample_id} | {o.title} | {_score_label(o)} | "
                     f"{_score_label(n)} | {delta} |")

    lines += ["", "## 3. 调整后仍存在的问题", ""]
    remaining = [r for r in new_results if r.issues]
    if not remaining:
        lines.append("无。所有样例均未发现问题。")
    else:
        for r in remaining:
            lines.append(f"### {r.sample_id} · {r.title}")
            lines.append("")
            for i in r.issues:
                tag = "🔴 错误" if i.severity == "error" else "🟡 警告"
                loc = f" `{i.where}`" if i.where else ""
                lines.append(f"- {tag}{loc} `{i.code}` — {i.message}")
            lines.append("")

    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = outdir / f"reaudit_{stamp}.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"对比报告：{out_path.resolve()}")
    return 0

def main(argv: list[str] | None = None) -> int:
    # Windows 控制台中文输出
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:                                  # pragma: no cover
                pass

    args = parse_args(argv)

    # 重新评分模式：不调用 API，只对历史结果套用当前规则
    if args.reaudit:
        return reaudit(Path(args.reaudit), Path(args.outdir))

    samples = collect_samples(args)
    if not samples:
        print("没有可用的样例。", file=sys.stderr)
        return 2

    # --dry-run：只打印提示词
    if args.dry_run:
        print("=" * 70)
        print(f"SYSTEM:\n{SYSTEM_PROMPT}")
        print("=" * 70)
        print(f"USER（样例 {samples[0]['id']} · {samples[0]['title']}）:\n")
        print(build_prompt(samples[0]["text"]))
        print("=" * 70)
        print(f"\n共 {len(samples)} 个样例，模型 {args.model}，"
              f"Base URL {args.base_url}")
        return 0

    # 自动加载 .env（脚本同目录优先，其次当前工作目录）
    loaded_env = load_env_files()

    api_key = resolve_api_key()
    if not args.mock:
        script_dir = Path(__file__).resolve().parent
        if not api_key:
            print(
                "[错误] 未找到 API Key。\n"
                "\n"
                "  两种配置方式，任选一种：\n"
                "\n"
                "  方式一（推荐）：在项目目录创建 .env 文件，写入下面这行：\n"
                "      DEEPSEEK_API_KEY=sk-你的key\n"
                f"      模板文件：{script_dir / '.env.example'}\n"
                "\n"
                "  方式二：设置系统环境变量（PowerShell）\n"
                "      $env:DEEPSEEK_API_KEY=\"sk-你的key\"\n"
                "\n"
                "  想先不花钱试一下？运行离线自检：\n"
                "      python quality_check.py --mock\n",
                file=sys.stderr,
            )
            return 1
        if looks_like_placeholder(api_key):
            print(
                f"[错误] 读取到的 API Key 看起来还是示例占位符：{mask_key(api_key)}\n"
                "  请把 .env 里的 DEEPSEEK_API_KEY 换成你自己的真实 Key。\n",
                file=sys.stderr,
            )
            return 1

    mode = "离线模拟" if args.mock else "在线调用"
    model = "内置模拟数据" if args.mock else args.model

    # 离线模式：用内置的「有缺陷 / 无缺陷」两份数据验证检查器本身
    if args.mock:
        plan: list[tuple[dict[str, str], dict[str, Any] | None]] = list(MOCK_SEQUENCE)
        if args.limit:
            plan = plan[: max(1, args.limit)]
        samples = [s for s, _ in plan]
    else:
        plan = [(s, None) for s in samples]

    print(f"[quality_check {VERSION}] 模式={mode} 样例={len(plan)} 模型={model}")
    if not args.mock:
        if loaded_env:
            print(f"[配置] 已加载 .env：{loaded_env[0]}")
        else:
            print("[配置] 未找到 .env 文件，使用系统环境变量")
        print(f"[配置] API Key：{mask_key(api_key)}")
        print(f"[配置] 接口地址：{args.base_url}")
    print("-" * 70)

    results: list[CaseResult] = []
    aborted_reason = ""
    for idx, (sample, mock_payload) in enumerate(plan, 1):
        prefix = f"[{idx}/{len(plan)}] {sample['id']} {sample['domain']}·{sample['title']}"
        print(f"{prefix} ... ", end="", flush=True)
        result = run_case(
            sample, mock=args.mock, mock_payload=mock_payload, api_key=api_key,
            base_url=args.base_url, model=args.model,
        )
        results.append(result)
        if result.error:
            print(f"失败（{result.error[:80]}）")
            if is_fatal_error(result.error):
                aborted_reason = result.error
                print()
                print("!" * 70)
                print("[已中止] 遇到无法通过重试解决的问题，后续样例不再执行。")
                print(f"  原因：{result.error[:200]}")
                print("  常见情况：HTTP 401 = API Key 无效或过期；"
                      "HTTP 402 = 账户余额不足；HTTP 403 = 无权限")
                print("  处理完之后重新运行即可；本次已完成的结果仍会生成报告。")
                print("!" * 70)
                print()
                break
        else:
            print(f"得分 {result.score}（错误 {result.n_error} / 警告 {result.n_warn}）"
                  f" {result.elapsed:.1f}s")

    # 输出报告
    outdir = Path(args.outdir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "model": model,
    }
    if aborted_reason:
        meta["aborted_reason"] = aborted_reason
    report_text = render_markdown(results, meta)
    report_path = outdir / f"quality_report_{stamp}.md"
    raw_path = outdir / f"raw_{stamp}.json"
    raw_text = json.dumps(
        {
            "meta": meta,
            "samples": [
                {
                    "id": s["id"], "domain": s["domain"], "title": s["title"],
                    "text": s["text"],
                }
                for s in samples
            ],
            "results": [
                {
                    "sample_id": r.sample_id,
                    "title": r.title,
                    "score": r.score,
                    "elapsed": round(r.elapsed, 2),
                    "error": r.error,
                    "parse_retries": r.parse_retries,
                    "raw_text": (r.raw_text[:8000] if r.error else ""),
                    "issues": [
                        {"severity": i.severity, "code": i.code,
                         "message": i.message, "where": i.where}
                        for i in r.issues
                    ],
                    "payload": r.payload,
                }
                for r in results
            ],
        },
        ensure_ascii=False, indent=2,
    )

    ok_results = [r for r in results if r.payload is not None]
    avg = sum(r.score for r in ok_results) / len(ok_results) if ok_results else 0.0

    print("-" * 70)
    print(f"生成成功 {len(ok_results)}/{len(results)}  |  "
          f"平均得分(成功样例) {avg:.1f}/100  |  "
          f"错误 {sum(r.n_error for r in results)}  |  "
          f"警告 {sum(r.n_warn for r in results)}")

    try:
        outdir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")
        raw_path.write_text(raw_text, encoding="utf-8")
        print(f"报告：{report_path.resolve()}")
        print(f"原始：{raw_path.resolve()}")
    except OSError as exc:
        # 常见原因：目录被安全软件/沙箱拦截、磁盘只读、路径无权限。
        # 这时直接把报告打到屏幕上，保证结果不会丢。
        print()
        print(f"[警告] 无法写入报告目录：{outdir.resolve()}")
        print(f"       原因：{exc}")
        print("       已改为直接输出到屏幕，你可以手动复制保存。")
        print(f"       也可以用 --outdir 指定一个可写目录，例如："
              f"--outdir \"{Path.home() / 'quality_reports'}\"")
        print()
        print("=" * 70)
        print(report_text)
        print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
