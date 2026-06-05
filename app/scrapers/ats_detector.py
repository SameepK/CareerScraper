"""Identify which ATS is hosting a job board from the URL."""
from enum import Enum
import re


class ATS(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    AVATURE = "avature"
    ORACLE_HCM = "oracle_hcm"
    IBM = "ibm"
    GENERIC = "generic"


_PATTERNS: list[tuple[re.Pattern, ATS]] = [
    (re.compile(r"greenhouse\.io", re.I), ATS.GREENHOUSE),
    (re.compile(r"lever\.co", re.I), ATS.LEVER),
    (re.compile(r"ashbyhq\.com", re.I), ATS.ASHBY),
    (re.compile(r"myworkdayjobs\.com|workday\.com", re.I), ATS.WORKDAY),
    (re.compile(r"avature\.net", re.I), ATS.AVATURE),
    (re.compile(r"fa\.oraclecloud\.com.*hcmUI|taleo\.net|oraclecorp\.com.*hcm", re.I), ATS.ORACLE_HCM),
    (re.compile(r"careers\.ibm\.com", re.I), ATS.IBM),
]


def detect_ats(url: str) -> ATS:
    for pattern, ats in _PATTERNS:
        if pattern.search(url):
            return ats
    return ATS.GENERIC
