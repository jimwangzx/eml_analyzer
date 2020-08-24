from dataclasses import dataclass
from functools import partial
from typing import List, Optional

import aiometer
import vt
from loguru import logger

from app.core.settings import VIRUSTOTAL_API_KEY
from app.schemas.verdict import Detail, Verdict


@dataclass
class VirusTotalVerdict:
    malicious: int
    sha256: str

    @property
    def link(self) -> str:
        return f"https://www.virustotal.com/gui/file/{self.sha256}/detection"

    @property
    def description(self) -> str:
        return f"{self.malicious} reports say {self.sha256} is malicious."


async def get_file(client: vt.Client, sha256: str) -> Optional[vt.Object]:
    try:
        return await client.get_object_async(f"/files/{sha256}")
    except Exception as e:
        logger.exception(e)
    return None


async def bulk_get_files(sha256s: List[str]) -> List[vt.Object]:
    if VIRUSTOTAL_API_KEY == "":
        return []

    if len(sha256s) == 0:
        return []

    client = vt.Client(str(VIRUSTOTAL_API_KEY))
    files = await aiometer.run_all(
        [partial(get_file, client, sha256) for sha256 in sha256s]
    )
    return [file_ for file_ in files if file_ is not None]


async def get_virustotal_verdicts(sha256s: List[str]) -> List[VirusTotalVerdict]:
    if VIRUSTOTAL_API_KEY == "":
        return []

    files = await bulk_get_files(sha256s)

    verdicts: List[VirusTotalVerdict] = []
    for file_ in files:
        malicious = int(file_.last_analysis_stats.get("malicious", 0))
        sha256 = str(file_.sha256)
        verdicts.append(VirusTotalVerdict(malicious=malicious, sha256=sha256))

    return verdicts


class VirusTotalVerdictFactory:
    def __init__(self, sha256s: List[str]):
        self.sha256s = sha256s
        self.name = "VirusTotal"

    async def to_model(self) -> Verdict:
        malicious_verdicts: List[VirusTotalVerdict] = []

        verdicts = await get_virustotal_verdicts(self.sha256s)
        for verdict in verdicts:
            if verdict.malicious > 0:
                malicious_verdicts.append(verdict)

        if len(malicious_verdicts) == 0:
            return Verdict(
                name=self.name,
                malicious=False,
                details=[
                    Detail(
                        key="benign", description="There is no malicious attachment.",
                    )
                ],
            )

        details: List[Detail] = []
        details = [
            Detail(
                key=verdict.sha256,
                score=verdict.malicious,
                description=verdict.description,
            )
            for verdict in malicious_verdicts
        ]
        return Verdict(name=self.name, malicious=True, score=100, details=details)

    @classmethod
    async def from_sha256s(cls, sha256s: List[str]) -> Verdict:
        obj = cls(sha256s)
        return await obj.to_model()
