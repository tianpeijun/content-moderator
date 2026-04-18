"""Pre-filter engine for fast keyword/regex-based content screening.

Scans text against configurable rules before calling the AI model.
If a rule matches, returns an immediate result without AI invocation.

Rule categories:
- privacy_leak: phone numbers, emails, ID cards, social IDs
- spam: URLs, promotional keywords, contact-harvesting phrases
- toxic: profanity (中/英), personal attacks
- hate_speech: discriminatory slurs
- misleading: medical / financial false claims
- illegal_trade: drugs, weapons, counterfeit

Patterns are designed to catch *obvious* violations. Edge cases and
context-sensitive content still go to the AI model.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PreFilterRule:
    """A single pre-filter rule."""
    name: str
    pattern: str  # regex pattern
    text_label: str  # label to assign on match
    action: str  # reject / flag
    compiled: re.Pattern = field(init=False, repr=False)

    def __post_init__(self):
        self.compiled = re.compile(self.pattern, re.IGNORECASE | re.MULTILINE)


@dataclass
class PreFilterResult:
    """Result of pre-filter scanning."""
    matched: bool = False
    text_label: str = "safe"
    action: str = "pass"
    rule_name: str = ""
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Pattern building blocks
# ---------------------------------------------------------------------------

# Chinese profanity (common, covers obfuscation like 操/艹/草/cao, 傻b/sb)
_CN_PROFANITY_WORDS = [
    "傻逼", "傻b", "煞笔", "sb", "妈的", "他妈", "操你", "艹你", "草泥马",
    "垃圾", "狗东西", "去死", "滚蛋", "废物", "脑残", "智障", "白痴",
    "骗子", "骗人", "诈骗", "坑爹", "缺德",
    "你妈", "妈逼", "泥马",
]

# English profanity (explicit, common)
_EN_PROFANITY_WORDS = [
    "fuck", "shit", "asshole", "bitch", "bastard", "dickhead",
    "motherfucker", "scum", "scumbag",
]

# Hate speech triggers (中/英)
_HATE_WORDS = [
    # 英文仇恨语
    r"go back to your country",
    r"your kind",
    r"(?:hate|kill)\s+(?:all\s+)?(?:gays|jews|blacks|asians|muslims|whites)",
    r"n[\*i]gg[ae]r",
    # 中文歧视词
    "支那", "倭寇", "鞑子",
    "滚回(?:你的)?(?:国家|老家)",
]

# Medical / weight-loss misleading claims
_MEDICAL_CLAIMS = [
    r"(?:FDA|FDA认证|FDA批准)\s*(?:approved|certified)?",
    r"(?:包治|根治|彻底治愈|立刻见效|一次治愈)",
    r"(?:神药|特效药|祖传秘方)",
    r"lose\s+\d+\s*(?:kg|kgs|pounds|lbs|磅|公斤)\s*in\s+(?:\d+\s*(?:days?|weeks?|months?|天|周|月)|one\s+\w+)",
    r"瘦\s*\d+\s*(?:斤|公斤|kg)",
    r"(?:100%|百分百|绝对)\s*(?:有效|治愈|见效)",
]

# Ad / spam promotional patterns (扩展后)
_SPAM_PHRASES = [
    r"加\s*V信?",
    r"加\s*微",
    r"扫码领",
    r"领\s*(?:优惠|红包|礼品|免费)",
    r"厂家直销",
    r"代购",
    r"(?:点击|戳我)\s*(?:链接|购买)",
    r"二维码",
    r"(?:BUY|buy)\s+(?:FOLLOWERS|NOW|CHEAP)",
    r"50%\s*OFF",
    r"免费\s*(?:赠送|领取)",
    r"私信\s*(?:我|有|领)",
    r"V\s*X\s*[:：]",       # vx:xxx
    r"vx\s*[:：]",
    r"(?:扣扣|QQ)\s*[:：]?\s*\d{5,}",
    r"(?:shop|store|buy)[a-z0-9\-]*\.(?:com|cn|net|co|shop|xyz|top)",
]

# Illegal / prohibited trade keywords
_ILLEGAL_PHRASES = [
    r"(?:出售|收购|代购)\s*(?:枪支|毒品|海洛因|冰毒|大麻|可卡因)",
    r"(?:发票|假证|假\s*文凭|代办证件)",
    r"(?:sell|buy)\s+(?:drugs|weed|cocaine|heroin|meth|guns?|firearms?)",
]

# Helper to build an alternation pattern from a word list
def _alt(words: list[str]) -> str:
    return r"(?:" + r"|".join(words) + r")"


# ---------------------------------------------------------------------------
# Default rules — ordered by specificity (more specific first)
# ---------------------------------------------------------------------------
DEFAULT_RULES: list[PreFilterRule] = [
    # ------------------------------------------------------------------
    # Privacy leak (highest priority — typically accompanies other violations)
    # ------------------------------------------------------------------
    PreFilterRule(
        name="中国手机号",
        pattern=r"1[3-9]\d{9}",
        text_label="privacy_leak",
        action="reject",
    ),
    PreFilterRule(
        name="中国身份证号",
        pattern=r"\d{17}[\dXx]",
        text_label="privacy_leak",
        action="reject",
    ),
    PreFilterRule(
        name="邮箱地址",
        pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        text_label="privacy_leak",
        action="reject",
    ),
    PreFilterRule(
        name="国际电话格式",
        pattern=r"\+\d{1,3}[\s\-]?\d{7,14}",
        text_label="privacy_leak",
        action="reject",
    ),
    PreFilterRule(
        name="微信/QQ/社交ID",
        pattern=r"(?:微信|wechat|wx|加我|联系我|QQ|扣扣|v信|v-x|vx)\s*[:：]?\s*[a-zA-Z0-9_\-]{5,}",
        text_label="privacy_leak",
        action="reject",
    ),
    PreFilterRule(
        name="日韩电话号码",
        pattern=r"(?:0\d{1,3}-?\d{4}-?\d{4}|010-?\d{4}-?\d{4}|090-?\d{4}-?\d{4})",
        text_label="privacy_leak",
        action="reject",
    ),

    # ------------------------------------------------------------------
    # Illegal trade (高优先 — 明确违法,不走模型)
    # ------------------------------------------------------------------
    *[
        PreFilterRule(
            name=f"违法交易-{i}",
            pattern=p,
            text_label="illegal_trade",
            action="reject",
        )
        for i, p in enumerate(_ILLEGAL_PHRASES, start=1)
    ],

    # ------------------------------------------------------------------
    # Hate speech
    # ------------------------------------------------------------------
    PreFilterRule(
        name="仇恨言论",
        pattern=_alt(_HATE_WORDS),
        text_label="hate_speech",
        action="reject",
    ),

    # ------------------------------------------------------------------
    # Misleading medical / financial claims
    # ------------------------------------------------------------------
    PreFilterRule(
        name="虚假医疗宣传",
        pattern=_alt(_MEDICAL_CLAIMS),
        text_label="misleading",
        action="reject",
    ),

    # ------------------------------------------------------------------
    # Toxic / profanity
    # ------------------------------------------------------------------
    PreFilterRule(
        name="中文辱骂",
        pattern=_alt([re.escape(w) for w in _CN_PROFANITY_WORDS]),
        text_label="toxic",
        action="reject",
    ),
    PreFilterRule(
        name="英文辱骂",
        # \b for English words (word boundary works fine)
        pattern=r"\b" + _alt(_EN_PROFANITY_WORDS) + r"\b",
        text_label="toxic",
        action="reject",
    ),

    # ------------------------------------------------------------------
    # Spam (keep last — most permissive, should only fire when no other category matched)
    # ------------------------------------------------------------------
    PreFilterRule(
        name="推广链接",
        pattern=r"(?:https?://|www\.)[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}",
        text_label="spam",
        action="reject",
    ),
    PreFilterRule(
        name="引流推广词",
        pattern=_alt(_SPAM_PHRASES),
        text_label="spam",
        action="reject",
    ),
]


class PreFilterEngine:
    """Fast keyword/regex pre-filter for content moderation.

    Scans text against a list of rules. If any rule matches,
    returns an immediate result without needing AI model invocation.

    Rules are evaluated in order. The first match wins — that's why
    privacy_leak / illegal_trade are listed before spam (more serious
    violations take precedence when a message triggers multiple rules).
    """

    def __init__(self, rules: list[PreFilterRule] | None = None):
        self.rules = rules if rules is not None else DEFAULT_RULES

    def scan(self, text: str | None) -> PreFilterResult:
        """Scan text against all pre-filter rules.

        Returns PreFilterResult with matched=True if any rule hits.
        """
        if not text or not text.strip():
            return PreFilterResult(matched=False)

        for rule in self.rules:
            if rule.compiled.search(text):
                logger.info(
                    "Pre-filter hit: rule='%s' label='%s'",
                    rule.name, rule.text_label,
                )
                return PreFilterResult(
                    matched=True,
                    text_label=rule.text_label,
                    action=rule.action,
                    rule_name=rule.name,
                    confidence=1.0,
                )

        return PreFilterResult(matched=False)
