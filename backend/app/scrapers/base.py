from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Item:
    name: str
    price: float
    currency: str = "AZN"
    in_stock: bool = True
    url: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "price": self.price, "currency": self.currency, "in_stock": self.in_stock, "url": self.url}


@dataclass
class SiteConfig:
    """Bir saytın scraping konfiqurasiyası. strategy: static (requests+BeautifulSoup) | api | selenium."""
    id: str                       # konfiq açarı
    site: str                     # məhsulların tarixçəsinin yazıldığı ad (strategiyadan asılı olmayaraq eyni)
    start_url: str
    strategy: str = "static"
    item_selector: str = "article.product"
    name_selector: str = "h3 a"
    name_attr: Optional[str] = "title"      # ad atributdadırsa (başlıq kəsilə bilər), yoxsa mətndən
    price_selector: str = "p.price"
    stock_selector: Optional[str] = None
    link_selector: str = "h3 a"
    next_selector: Optional[str] = None
    max_pages: int = 5
    default_currency: str = "AZN"
    wait_selector: Optional[str] = None     # selenium: bunu gözlə
    api_url: Optional[str] = None


@dataclass
class ScrapeResult:
    items: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    pages: int = 0
    strategy: str = "static"
