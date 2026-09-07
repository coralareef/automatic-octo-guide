from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetaTarget:
    month: str = "2026-08"
    format: str = "gen9ou"
    rating: int = 1825

    @property
    def chaos_url(self) -> str:
        return (
            f"https://www.smogon.com/stats/{self.month}/chaos/"
            f"{self.format}-{self.rating}.json.gz"
        )
